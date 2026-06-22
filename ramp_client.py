"""Ramp transaction extraction.

In live mode (RAMP_CLIENT_ID + RAMP_CLIENT_SECRET) this would pull card
transactions from Ramp's developer API. For the demo it loads a bundled sample
with the same field shape Ramp returns, then normalizes it to the facts the
deductibility check needs.

The jurisdiction (the tax home of the entity that incurred the spend) isn't on a
single transaction in Ramp — it comes from the Ramp business/entity. For the demo
each sample carries an `entity_country`; live, you'd resolve it from the entity.
"""

from __future__ import annotations

import json
import os

RAMP_CLIENT_ID = os.environ.get("RAMP_CLIENT_ID")
RAMP_CLIENT_SECRET = os.environ.get("RAMP_CLIENT_SECRET")


def extract(source: str) -> list[dict]:
    """Return a list of Ramp-shaped transactions.

    source: a path to a bundled sample .json (a list of transactions). In live
    mode the samples are ignored and transactions are pulled from the API.
    """
    if RAMP_CLIENT_ID and RAMP_CLIENT_SECRET:
        return _extract_live()
    with open(source) as fh:
        data = json.load(fh)
    return data if isinstance(data, list) else [data]


def _extract_live() -> list[dict]:  # pragma: no cover - needs real credentials
    """Live Ramp pull. Wired but inert until credentials are present.

    Ramp uses OAuth2 client-credentials, then GET /developer/v1/transactions.
    """
    import base64
    import urllib.request

    creds = base64.b64encode(f"{RAMP_CLIENT_ID}:{RAMP_CLIENT_SECRET}".encode()).decode()
    token_req = urllib.request.Request(
        "https://api.ramp.com/developer/v1/token",
        data=b"grant_type=client_credentials&scope=transactions:read",
        headers={
            "Authorization": f"Basic {creds}",
            "Content-Type": "application/x-www-form-urlencoded",
        },
    )
    with urllib.request.urlopen(token_req, timeout=30) as r:
        token = json.load(r)["access_token"]
    tx_req = urllib.request.Request(
        "https://api.ramp.com/developer/v1/transactions?page_size=25",
        headers={"Authorization": f"Bearer {token}"},
    )
    with urllib.request.urlopen(tx_req, timeout=30) as r:
        return json.load(r).get("data", [])


def normalize(tx: dict) -> dict:
    """Reduce a Ramp transaction to the facts the deductibility check needs."""
    holder = tx.get("card_holder") or {}
    name = " ".join(filter(None, [holder.get("first_name"), holder.get("last_name")]))
    return {
        "merchant": tx.get("merchant_name", ""),
        "amount": float(tx.get("amount", 0)),
        "currency": tx.get("currency_code", "USD"),
        "ramp_category": tx.get("sk_category_name", ""),
        "memo": tx.get("memo", "") or "",
        "card_holder": name,
        "jurisdiction": (tx.get("entity_country") or "").upper(),
    }
