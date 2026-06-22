"""Apply the loaded OpenAccountants deductibility rules to a Ramp transaction.

Two steps:
  1. classify() maps a Ramp category/memo/merchant to a tax category that exists
     in the loaded skill's rules (this is the bit an AI agent does live by
     reasoning over the skill; here it's a transparent keyword mapper).
  2. check() looks up the rule and returns the verdict.

DELIBERATE SIMPLIFICATION: covers the handful of categories the samples need.
Production leans on the full OA skill + an agent step; the named-CPA sign-off is
what makes the verdict relianceable.
"""

from __future__ import annotations


def classify(jurisdiction: str, ramp_category: str, memo: str, merchant: str) -> str | None:
    t = f"{ramp_category} {memo} {merchant}".lower()
    has = lambda *ks: any(k in t for k in ks)

    is_client = has("client", "prospect", "customer")
    is_staff = has("staff", "team", "employee")
    is_meal = has("meal", "dinner", "lunch", "restaurant", "grill", "cafe", "bistro", "food")
    is_entertain = has("entertain", "ticket", "event", "game", "nba", "nfl", "concert", "theatre", "theater", "golf")
    is_software = has("software", "subscription", "saas", "web service", "figma", "slack", "github", "notion", "aws", "adobe")
    is_office = has("office", "supplies", "stationery", "staples")
    is_travel = has("travel", "flight", "airline", "hotel", "uber", "lyft", "taxi", "rail", "train")

    if jurisdiction == "GB":
        if is_staff and is_entertain:
            return "staff_entertainment"
        if (is_client and (is_meal or is_entertain)) or is_entertain:
            return "client_entertainment"
        if is_software:
            return "software"
        if is_office:
            return "office_supplies"
        if is_travel:
            return "travel"
        return None

    # US: meals (50%) and entertainment (0%) are treated differently
    if is_entertain and not is_meal:
        return "entertainment"
    if is_meal:
        return "client_meals"
    if is_software:
        return "software"
    if is_office:
        return "office_supplies"
    if is_travel:
        return "travel"
    return None


def _vat_line(jurisdiction: str, rule: dict) -> str:
    vr = rule.get("vat_recoverable")
    if vr is None:
        return ""  # no VAT regime (e.g. US)
    return " Input VAT recoverable." if vr else " Input VAT NOT recoverable."


def check(facts: dict, oa_skill: dict) -> dict:
    rules = oa_skill.get("rules", {})
    base = {
        "oa_skill": oa_skill.get("slug"),
        "oa_skill_name": oa_skill.get("name"),
        "tier": oa_skill.get("tier"),
        "verifier": oa_skill.get("verifier"),
        "source": oa_skill.get("source"),
    }
    j = facts["jurisdiction"]
    cat = classify(j, facts["ramp_category"], facts["memo"], facts["merchant"])
    rule = rules.get(cat) if cat else None

    if not rule:
        return {**base, "status": "info", "tax_category": cat,
                "headline": "Outside this demo's rule set",
                "detail": f"Couldn't map '{facts['ramp_category']}' to a covered category — full skill / agent step needed.",
                "basis": "n/a"}

    ded = rule["deductible"]
    vat = _vat_line(j, rule)

    if ded == "yes":
        return {**base, "status": "ok", "tax_category": cat,
                "headline": "Deductible" + (" · VAT recoverable" if "recoverable." in vat and "NOT" not in vat else ""),
                "detail": rule["basis"], "basis": rule["basis"]}
    if ded == "no":
        return {**base, "status": "warn", "tax_category": cat,
                "headline": "NOT deductible" + (" · VAT blocked" if "NOT recoverable" in vat else ""),
                "detail": rule["basis"], "basis": rule["basis"]}
    if ded == "partial":
        pct = int(rule.get("deductible_pct", 0) * 100)
        return {**base, "status": "info", "tax_category": cat,
                "headline": f"Only {pct}% deductible — document business purpose",
                "detail": rule["basis"], "basis": rule["basis"]}
    # conditional
    return {**base, "status": "info", "tax_category": cat,
            "headline": "Deductible only if conditions are met",
            "detail": rule["basis"] + vat, "basis": rule["basis"]}
