"""Write Dokploy provider keys into ~/.openbb_platform/user_settings.json.

PyPI OpenBB in this image loads credentials from that file. An empty file
created on first boot would otherwise hide FRED_API_KEY / FMP_API_KEY.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

_ENV_TO_CREDENTIAL = (
    ("FRED_API_KEY", "fred_api_key"),
    ("fred_api_key", "fred_api_key"),
    ("FMP_API_KEY", "fmp_api_key"),
    ("fmp_api_key", "fmp_api_key"),
)


def main() -> None:
    path = Path.home() / ".openbb_platform" / "user_settings.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    data: dict = {}
    if path.exists():
        try:
            loaded = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            loaded = {}
        if isinstance(loaded, dict):
            data = loaded
    credentials = dict(data.get("credentials") or {})
    for env_name, cred_name in _ENV_TO_CREDENTIAL:
        value = os.environ.get(env_name, "").strip()
        if value:
            credentials[cred_name] = value
    data["credentials"] = credentials
    path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
    os.execvp("openbb-api", ["openbb-api", "--host", "0.0.0.0", *sys.argv[1:]])
