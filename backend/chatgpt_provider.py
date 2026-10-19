"""OAuth Responses transport. Fixed public endpoint; no credential export."""
import asyncio
import codecs
import json
import httpx
from fastapi import HTTPException, Request
from .oauth import COOKIE, RESOURCE, client, oauth, router

MAX_STREAM = 256 * 1024
MAX_MODEL_CATALOG = 8 * 1024 * 1024


async def bounded_lines(response):
    decoder = codecs.getincrementaldecoder("utf-8")("strict")
    pending = ""
    size = 0
    async for chunk in response.aiter_bytes():
        size += len(chunk)
        if size > MAX_STREAM:
            provider_error("incomplete_response")
        pending += decoder.decode(chunk)
        while "\n" in pending:
            line, pending = pending.split("\n", 1)
            yield line.rstrip("\r")
    pending += decoder.decode(b"", final=True)
    if pending:
        yield pending.rstrip("\r")



def provider_error(code, status=502):
    messages = {
        "subscription_sharing_usage_limit_exceeded": "La limite d’utilisation du forfait ChatGPT est atteinte. Consultez Usage dans ChatGPT.",
        "subscription_sharing_usage_unavailable": "L’utilisation du forfait ChatGPT est temporairement indisponible.",
        "unsupported_plan": "Ce compte ou forfait ne permet pas cette utilisation. Vérifiez les conditions dans ChatGPT.",
        "consent_required": "Autorisez l’utilisation de votre forfait ChatGPT avant de réessayer.",
        "session_expired": "La session ChatGPT a expiré. Reconnectez-vous.",
        "incomplete_response": "La génération a été interrompue. Aucune proposition partielle n’est affichée.",
    }
    raise HTTPException(status, {"code": code if code in messages else "provider_error",
                               "message": messages.get(code, "ChatGPT n’a pas pu terminer cette génération. Réessayez.")})


async def catalog(browser):
    token = await oauth.access(browser)
    try:
        data = await oauth.json_request("GET", RESOURCE + "/models", max_bytes=MAX_MODEL_CATALOG,
                                        headers={"Authorization": "Bearer " + token})
        models = data.get("models")
        if not isinstance(models, list):
            raise ValueError()
        return [{"slug": item["slug"], "display_name": item["display_name"]} for item in models
                if isinstance(item, dict) and item.get("visibility") == "list"
                and isinstance(item.get("slug"), str) and isinstance(item.get("display_name"), str)]
    except HTTPException as exc:
        if exc.status_code == 401 and oauth.session and oauth.session.access == token:
            oauth.session = None
            oauth.error = {"code": "reauth_required", "message": "La session doit être reconnectée."}
        raise
    except (httpx.HTTPError, ValueError, TimeoutError):
        provider_error("provider_error")


@router.get("/models")
async def models(request: Request):
    return {"models": await catalog(request.cookies.get(COOKIE))}


async def stream_text(browser, model, instructions, user_data):
    task = asyncio.current_task()
    oauth.generations.add(task)
    try:
        return await _stream_text(browser, model, instructions, user_data)
    finally:
        oauth.generations.discard(task)


async def _stream_text(browser, model, instructions, user_data):
    # Validate against this account's current catalog; never assume plan eligibility.
    available = await catalog(browser)
    if model not in {item["slug"] for item in available}:
        raise HTTPException(422, "Choisissez un modèle disponible pour ce compte ChatGPT.")
    token = await oauth.access(browser)
    payload = {"model": model, "instructions": instructions,
               "input": [{"role": "user", "content": user_data}], "store": False, "stream": True}
    try:
        async with asyncio.timeout(60):
            async with client() as http:
                async with http.stream("POST", RESOURCE + "/responses", json=payload,
                        headers={"Authorization": "Bearer " + token, "Content-Type": "application/json", "Accept": "text/event-stream"}) as response:
                    if response.status_code == 401:
                        if oauth.session and oauth.session.access == token:
                            oauth.session = None
                            oauth.error = {"code": "reauth_required", "message": "La session doit être reconnectée."}
                        provider_error("session_expired", 401)
                    if response.status_code == 403:
                        provider_error("unsupported_plan", 403)
                    if response.status_code == 429:
                        provider_error("subscription_sharing_usage_limit_exceeded", 429)
                    if response.status_code >= 300 or "text/event-stream" not in response.headers.get("content-type", ""):
                        provider_error("provider_error")
                    size, text, fields, completed = 0, [], [], False
                    async for line in bounded_lines(response):
                        size += len(line.encode("utf-8")) + 1
                        if size > MAX_STREAM:
                            provider_error("incomplete_response")
                        if line.startswith("data:"):
                            fields.append(line[5:].lstrip(" "))
                        elif line == "" and fields:
                            raw, fields = "\n".join(fields), []
                            if raw == "[DONE]":
                                continue
                            event = json.loads(raw)
                            if completed:
                                provider_error("incomplete_response")
                            kind = event.get("type")
                            if kind == "response.output_text.delta":
                                delta = event.get("delta")
                                if not isinstance(delta, str):
                                    raise ValueError()
                                text.append(delta)
                            elif kind in {"response.failed", "response.incomplete", "error"}:
                                error = event.get("response", {}).get("error") or event.get("error") or event
                                provider_error(error.get("code", "incomplete_response"))
                            elif kind == "response.completed":
                                if event.get("response", {}).get("status") != "completed":
                                    provider_error("incomplete_response")
                                completed = True
                    if not completed or fields or not text:
                        provider_error("incomplete_response")
                    return "".join(text)
    except HTTPException:
        raise
    except (httpx.TimeoutException, TimeoutError):
        raise HTTPException(504, "ChatGPT met trop de temps à répondre. Réessayez.") from None
    except (httpx.HTTPError, ValueError, TypeError, AttributeError):
        provider_error("incomplete_response")
