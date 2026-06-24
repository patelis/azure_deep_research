"""Mint a per-user access key for the app's env key store.

    uv run python utils/mint_key.py "Alice"

Prints the secret key (give it to the user) and the ``name:sha256hash`` entry to add to the
``API_KEYS`` env var / azd env (only the hash is stored; the secret is shown once).
"""

from __future__ import annotations

import secrets
import sys

from deep_research.keystore import hash_key


def main() -> int:
    name = sys.argv[1] if len(sys.argv) > 1 else "user"
    key = secrets.token_urlsafe(24)
    print(f"Access key for {name!r} (share securely, shown once):\n  {key}\n")
    print("Add this entry to API_KEYS (comma-separated):")
    print(f"  {name}:{hash_key(key)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
