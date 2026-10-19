"""Private owner ChatGPT session used by the invitation-only hosted beta.

The session is created by the owner through the existing local SIWC flow and
copied to the server as an encrypted file. No public route can start OAuth or
read the owner's browser identifier, account identity, or tokens.
"""

from __future__ import annotations

import asyncio
import os

from fastapi import HTTPException

from .chatgpt_provider import catalog, stream_text
from .oauth import CredentialStoreError, enabled, load_persistent_session, oauth

UNAVAILABLE = "Le service de génération est momentanément indisponible. Réessayez plus tard."
REQUIRED_SCOPE = "chatgpt.tokens.use.direct"


class OwnerProviderError(HTTPException):
    """Public response stays generic; private diagnostics keep only a category."""
    def __init__(self, reason: str):
        super().__init__(503, UNAVAILABLE)
        self.reason = reason


def unavailable(error: Exception) -> OwnerProviderError:
    if isinstance(error, OwnerProviderError):
        return error
    if isinstance(error, CredentialStoreError):
        return OwnerProviderError("credentials")
    if isinstance(error, HTTPException):
        code = error.detail.get("code") if isinstance(error.detail, dict) else None
        if code in {"subscription_sharing_usage_limit_exceeded", "subscription_sharing_usage_unavailable"}:
            return OwnerProviderError("quota")
        if code in {"unsupported_plan", "consent_required", "session_expired"}:
            return OwnerProviderError("authorization")
        if code == "incomplete_response":
            return OwnerProviderError("invalid_response")
        return OwnerProviderError({429: "quota", 401: "authorization", 403: "authorization",
                                   422: "model"}.get(error.status_code, "provider"))
    return OwnerProviderError("provider")


def stored_owner():
    if not enabled() or not os.getenv("REPLIQUE_CREDENTIAL_KEY_FILE"):
        raise OwnerProviderError("credentials")
    try:
        session = load_persistent_session("", owner=True)
    except CredentialStoreError:
        raise OwnerProviderError("credentials") from None
    if session is None or REQUIRED_SCOPE not in session.scopes or "resource.invoke" not in session.scopes:
        raise OwnerProviderError("credentials")
    return session


async def owner_browser() -> str:
    try:
        stored = stored_owner()
    except (HTTPException, CredentialStoreError) as error:
        raise unavailable(error) from None
    async with oauth.lock:
        if (oauth.session is None or oauth.session.browser != stored.browser
                or oauth.session.refresh != stored.refresh):
            oauth.session = stored
        return oauth.session.browser


async def owner_model() -> tuple[str, str]:
    browser = await owner_browser()
    preferred = os.getenv("REPLIQUE_MODEL", "").strip()
    if not preferred:
        raise OwnerProviderError("configuration")
    return browser, preferred


async def generate_text(instructions: str, user_data: str) -> str:
    browser, model = await owner_model()
    try:
        return await stream_text(browser, model, instructions, user_data)
    except (HTTPException, CredentialStoreError) as error:
        raise unavailable(error) from None


async def check_models() -> list[str]:
    browser = await owner_browser()
    models = await catalog(browser)
    return [item["slug"] for item in models]


if __name__ == "__main__":
    # Owner-only diagnostic from inside the container; never prints credentials.
    available = asyncio.run(check_models())
    if not available:
        raise SystemExit("Aucun modèle éligible pour cette session.")
    for slug in available:
        print(slug)
