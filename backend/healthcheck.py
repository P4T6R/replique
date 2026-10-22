"""Probe the local app using its configured public Host header."""

import os
from urllib.parse import urlsplit
from urllib.request import Request, urlopen


def probe() -> bool:
    origin = os.getenv("REPLIQUE_PUBLIC_ORIGIN", "")
    host = urlsplit(origin).netloc if origin else "127.0.0.1:8000"
    request = Request("http://127.0.0.1:8000/api/health", headers={"Host": host})
    with urlopen(request, timeout=4) as response:
        return response.status == 200


if __name__ == "__main__":
    raise SystemExit(0 if probe() else 1)
