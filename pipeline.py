#!/usr/bin/env python3
"""Ramp -> OpenAccountants expense-deductibility pipeline.

    python pipeline.py                      # bundled sample feed (mock mode)
    python pipeline.py samples/transactions.json

The flow:
    Ramp transactions -> OA MCP (start -> get_skill) -> classify + apply rules -> verdict

Live: set OA_MCP_TOKEN (+ RAMP_CLIENT_ID / RAMP_CLIENT_SECRET) to pull real
transactions and verified rules instead of the bundled samples.
"""

from __future__ import annotations

import os
import sys

import deductibility_check
import ramp_client
from oa_client import OAClient

STATUS = {"ok": "✅", "warn": "⚠️ ", "info": "ℹ️ "}


def run(source: str, oa: OAClient) -> None:
    for tx in ramp_client.extract(source):
        f = ramp_client.normalize(tx)

        amt = f"{f['currency']} {f['amount']:.2f}"
        memo = f' · "{f["memo"]}"' if f["memo"] else ""
        print(f"\n💳  {f['merchant']} · {amt}{memo}  [{f['jurisdiction']} · {f['ramp_category']}]")

        plan = oa.start("Classify expense deductibility", f["jurisdiction"] or "EU")
        slug = (plan.get("skills_to_load") or [None])[0]
        skill = oa.get_skill(slug) if slug else {}

        v = deductibility_check.check(f, skill)

        trust = f"tier {v.get('tier')}" + (f", signed off by {v['verifier']}" if v.get("verifier") else "")
        print(f"    OpenAccountants → {v.get('oa_skill_name') or 'deductibility rules'}  ({trust})")
        print(f"    {STATUS.get(v['status'], '')} {v['headline']}")
        print(f"       {v['detail']}")
        if v["status"] == "warn":
            print("       → flag for review before it's booked as deductible")


def main(argv: list[str]) -> int:
    oa = OAClient()
    mode = "LIVE" if oa.live else "MOCK (set OA_MCP_TOKEN + RAMP creds to go live)"
    print(f"Ramp → OpenAccountants · expense-deductibility demo  [{mode}]")

    here = os.path.dirname(os.path.abspath(__file__))
    source = argv[1] if len(argv) > 1 else os.path.join(here, "samples", "transactions.json")
    run(source, oa)
    print()
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
