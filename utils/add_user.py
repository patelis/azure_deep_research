"""Manage users in the Table Storage key store (when API_KEY_STORE=table) — no redeploy needed.

    uv run python utils/add_user.py "Alice"            # mint a key + add the user (active now)
    uv run python utils/add_user.py --revoke "Alice"   # deactivate the user
    uv run python utils/add_user.py --list             # list users

Keyless via Entra ID (needs AZURE_TABLE_ENDPOINT + Storage Table Data Contributor). Only the
SHA-256 hash is stored; the secret key is printed once on creation.
"""

from __future__ import annotations

import argparse
import secrets
import sys

from deep_research.config import get_settings
from deep_research.keystore import hash_key

_KEY_PARTITION = "key"


def _client():
    from azure.data.tables import TableClient
    from azure.identity import DefaultAzureCredential

    cfg = get_settings()
    if not cfg.azure_table_endpoint:
        sys.exit("AZURE_TABLE_ENDPOINT is not set (API_KEY_STORE=table). Populate .env from IaC.")
    return TableClient(
        endpoint=cfg.azure_table_endpoint,
        table_name=cfg.api_keys_table,
        credential=DefaultAzureCredential(),
    )


def _add(name: str) -> None:
    key = secrets.token_urlsafe(24)
    digest = hash_key(key)
    with _client() as client:
        client.upsert_entity(
            {"PartitionKey": _KEY_PARTITION, "RowKey": digest, "Name": name, "Active": True}
        )
    print(f"Access key for {name!r} (share securely, shown once):\n  {key}")


def _revoke(name: str) -> None:
    with _client() as client:
        for e in client.query_entities(f"PartitionKey eq '{_KEY_PARTITION}' and Name eq '{name}'"):
            e["Active"] = False
            client.update_entity(e)
            print(f"Revoked {name!r} ({e['RowKey'][:12]}…).")


def _list() -> None:
    with _client() as client:
        for e in client.query_entities(f"PartitionKey eq '{_KEY_PARTITION}'"):
            state = "active" if e.get("Active", True) else "revoked"
            print(f"  {e.get('Name', 'user'):20} {state:8} {e['RowKey'][:12]}…")


def main() -> int:
    parser = argparse.ArgumentParser(description="Manage Table-Storage key-store users.")
    parser.add_argument("name", nargs="?", help="user name to add (or revoke with --revoke)")
    parser.add_argument("--revoke", action="store_true", help="deactivate the named user")
    parser.add_argument("--list", action="store_true", help="list users")
    args = parser.parse_args()

    if args.list:
        _list()
    elif args.revoke:
        if not args.name:
            sys.exit("--revoke requires a user name")
        _revoke(args.name)
    elif args.name:
        _add(args.name)
    else:
        parser.print_help()
    return 0


if __name__ == "__main__":
    sys.exit(main())
