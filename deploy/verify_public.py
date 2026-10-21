"""Read-only smoke check for the public hosted deployment.

Uses the normal system HTTPS proxy and certificate store. No account, token,
conversation, or image is sent to the service.
"""

from __future__ import annotations

import argparse
import json
import sys
from urllib.error import HTTPError, URLError
from urllib.parse import urljoin, urlsplit
from urllib.request import Request, urlopen


def read(url: str) -> tuple[str, bytes]:
    request = Request(url, headers={"Accept": "application/json, text/html", "Cache-Control": "no-cache"})
    with urlopen(request, timeout=20) as response:
        return response.geturl(), response.read(256 * 1024 + 1)


def verify(origin: str) -> None:
    parsed = urlsplit(origin)
    if (parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password
            or parsed.path not in {"", "/"} or parsed.query or parsed.fragment):
        raise ValueError("Indiquez une origine HTTPS publique, sans chemin ni paramètres.")
    base = origin.rstrip("/") + "/"
    page_url, page = read(base)
    if page_url != base or len(page) > 256 * 1024:
        raise ValueError("La page publique redirige ou dépasse la taille attendue.")
    if b'id="root"' not in page or b"/assets/" not in page:
        raise ValueError("Le domaine sert encore la page privée ou une version sans interface compilée.")
    health_url = urljoin(base, "api/health")
    actual_url, body = read(health_url)
    if actual_url != health_url or len(body) > 256 * 1024:
        raise ValueError("Le contrôle de santé redirige ou renvoie trop de données.")
    try:
        health = json.loads(body)
    except (UnicodeDecodeError, json.JSONDecodeError):
        raise ValueError("/api/health ne renvoie pas du JSON valide.") from None
    if health.get("mode") != "hosted" or health.get("provider") != "OpenAI" or health.get("ocr_available") is not True:
        raise ValueError("La bêta hébergée et la lecture des photos ne sont pas prêtes.")
    print("OK : interface publique, API hébergée et OCR disponibles. Tester ensuite avec un compte invité et une capture fictive.")


def main() -> None:
    parser = argparse.ArgumentParser(description="Vérifier la publication publique de Réplique sans données privées")
    parser.add_argument("--origin", default="https://replique.duckdns.org")
    args = parser.parse_args()
    try:
        verify(args.origin)
    except (ValueError, HTTPError, URLError, TimeoutError) as error:
        print(f"ÉCHEC du contrôle public : {error}", file=sys.stderr)
        raise SystemExit(1) from None


if __name__ == "__main__":
    main()
