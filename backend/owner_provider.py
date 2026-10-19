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


def stored_owner():
    if not enabled() or not os.getenv("REPLIQUE_CREDENTIAL_KEY_FILE"):
        raise HTTPException(503, UNAVAILABLE)
    try:
        session = load_persistent_session("", owner=True)
    except CredentialStoreError:
        raise HTTPException(503, UNAVAILABLE) from None
    if session is None or REQUIRED_SCOPE not in session.scopes or "resource.invoke" not in session.scopes:
        raise HTTPException(503, UNAVAILABLE)
    return session


async def owner_browser() -> str:
    stored = stored_owner()
    async with oauth.lock:
        if (oauth.session is None or oauth.session.browser != stored.browser
                or oauth.session.refresh != stored.refresh):
            oauth.session = stored
        return oauth.session.browser


async def owner_model() -> tuple[str, str]:
    browser = await owner_browser()
    preferred = os.getenv("REPLIQUE_MODEL", "").strip()
    if preferred:
        return browser, preferred
    try:
        models = await catalog(browser)
    except (HTTPException, CredentialStoreError):
        raise HTTPException(503, UNAVAILABLE) from None
    if not models:
        raise HTTPException(503, UNAVAILABLE)
    return browser, models[0]["slug"]


async def generate_text(instructions: str, user_data: str) -> str:
    browser, model = await owner_model()
    try:
        return await stream_text(browser, model, instructions, user_data)
    except (HTTPException, CredentialStoreError):
        raise HTTPException(503, UNAVAILABLE) from None


async def check_models() -> list[str]:
    browser = await owner_browser()
    models = await catalog(browser)
    return [item["slug"] for item in models]


if __name__ == "__main__":
    # Owner-only diagnostic from inside the container; never prints credentials.
    for slug in asyncio.run(check_models()):
        print(slug)
