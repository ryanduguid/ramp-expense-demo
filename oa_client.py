"""OpenAccountants MCP client.

Talks to the OpenAccountants MCP server over JSON-RPC 2.0 at
https://www.openaccountants.com/api/mcp. The MCP requires authentication on tool
calls, so a token (OA_MCP_TOKEN) is needed for live mode. Without one, this
client returns bundled sample responses that mirror the live shape so the demo
runs end to end.

  - start(intent, jurisdiction)  -> which verified skill governs the question
  - get_skill(slug)              -> the deductibility rules + tier + named verifier
"""

from __future__ import annotations

import json
import os
import urllib.request
import urllib.error

MCP_URL = os.environ.get("OA_MCP_URL", "https://www.openaccountants.com/api/mcp")
MCP_TOKEN = os.environ.get("OA_MCP_TOKEN")


class OAClient:
    def __init__(self, token: str | None = MCP_TOKEN, url: str = MCP_URL):
        self.token = token
        self.url = url
        self._id = 0

    @property
    def live(self) -> bool:
        return bool(self.token)

    def start(self, intent: str, jurisdiction: str) -> dict:
        if not self.live:
            return _MOCK_START.get(jurisdiction.upper(), _MOCK_START["_DEFAULT"])
        return self._call("start", {"intent": intent, "jurisdiction": jurisdiction})

    def get_skill(self, slug: str) -> dict:
        if not self.live:
            return _MOCK_SKILL.get(slug, _MOCK_SKILL["_DEFAULT"])
        return self._call("get_skill", {"slug": slug})

    def _call(self, tool: str, arguments: dict) -> dict:
        self._id += 1
        body = json.dumps(
            {"jsonrpc": "2.0", "id": self._id, "method": "tools/call",
             "params": {"name": tool, "arguments": arguments}}
        ).encode()
        headers = {"Content-Type": "application/json", "Accept": "application/json"}
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"  # scheme TBD; swap if OA uses apikey
        req = urllib.request.Request(self.url, data=body, headers=headers)
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                payload = json.load(resp)
        except urllib.error.HTTPError as e:
            raise RuntimeError(f"OA MCP HTTP {e.code}: {e.read().decode()[:300]}") from e
        if "error" in payload and payload["error"]:
            raise RuntimeError(f"OA MCP error: {payload['error']}")
        result = payload.get("result", {})
        if isinstance(result.get("structuredContent"), (dict, list)):
            return result["structuredContent"]
        text = (result.get("content") or [{}])[0].get("text", "{}")
        return json.loads(text)


# --- Bundled sample responses (mirror live MCP shape) ----------------------
# Verifier names are the real OpenAccountants jurisdiction leads. Live, every
# field here comes straight from get_skill.

_MOCK_START = {
    "GB": {"jurisdiction": "GB", "skills_to_load": ["gb-expense-deductibility"],
           "next_action": "Load the skill, then classify each expense."},
    "US": {"jurisdiction": "US", "skills_to_load": ["us-expense-deductibility"],
           "next_action": "Load the skill, then classify each expense."},
    "_DEFAULT": {"jurisdiction": "EU", "skills_to_load": ["expense-deductibility"],
                 "next_action": "Load the skill, then classify each expense."},
}

# Per tax-category rules: deductible (yes|partial|conditional|no), the VAT/input-tax
# recoverability, and a one-line basis. Illustrative — production reads the full
# skill markdown / an agent reasons over it.
_MOCK_SKILL = {
    "gb-expense-deductibility": {
        "slug": "gb-expense-deductibility",
        "name": "United Kingdom — expense deductibility & VAT recovery",
        "jurisdiction": "GB", "tier": 1, "verifier": "James Power (UK lead)",
        "rules": {
            "client_entertainment": {"deductible": "no", "vat_recoverable": False,
                "basis": "Client/business entertaining is not deductible for UK corporation tax (CTA 2009 s1298) and input VAT is blocked."},
            "staff_entertainment": {"deductible": "conditional", "vat_recoverable": True,
                "basis": "Annual staff event deductible up to £150/head; input VAT recoverable."},
            "software": {"deductible": "yes", "vat_recoverable": True, "basis": "Wholly-and-exclusively business cost; input VAT recoverable on a valid VAT invoice."},
            "office_supplies": {"deductible": "yes", "vat_recoverable": True, "basis": "Allowable business expense; input VAT recoverable."},
            "travel": {"deductible": "yes", "vat_recoverable": True, "basis": "Business travel allowable; input VAT recoverable."},
        },
        "source": "https://www.openaccountants.com/skills/gb-expense-deductibility",
    },
    "us-expense-deductibility": {
        "slug": "us-expense-deductibility",
        "name": "United States — business expense deductibility",
        "jurisdiction": "US", "tier": 1, "verifier": "Amir Pelinkovic (US lead)",
        "rules": {
            "client_meals": {"deductible": "partial", "deductible_pct": 0.5, "vat_recoverable": None,
                "basis": "Business meals 50% deductible (IRC §274(n)); keep business-purpose documentation."},
            "entertainment": {"deductible": "no", "vat_recoverable": None,
                "basis": "Entertainment is non-deductible post-TCJA (IRC §274(a))."},
            "software": {"deductible": "yes", "vat_recoverable": None, "basis": "Ordinary & necessary business expense (IRC §162)."},
            "office_supplies": {"deductible": "yes", "vat_recoverable": None, "basis": "Ordinary & necessary business expense (IRC §162)."},
            "travel": {"deductible": "yes", "vat_recoverable": None, "basis": "Business travel deductible (IRC §162(a)(2))."},
        },
        "source": "https://www.openaccountants.com/skills/us-expense-deductibility",
    },
    "_DEFAULT": {
        "slug": "expense-deductibility", "name": "Expense deductibility",
        "jurisdiction": "EU", "tier": 2, "verifier": None, "rules": {},
        "source": "https://www.openaccountants.com/skills",
    },
}
