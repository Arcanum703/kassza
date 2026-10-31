"""Ordinary code that checks the model. The model reads the receipt; code does the maths.

Every check returns a dict {id, ok, message}. A receipt is accepted only if all pass.
"""
import re
from datetime import date

from . import country
from .schema import Receipt

TOL = 1.0  # HUF: per-line rounding on printed receipts


def vat_split(receipt: Receipt, cfg: dict | None = None) -> list[dict]:
    """Net / VAT per code, computed from item gross amounts (never from the model)."""
    cfg = cfg or country.load()
    groups: dict[str, float] = {}
    for it in receipt.items:
        groups[it.vat_code.upper()] = groups.get(it.vat_code.upper(), 0) + it.amount
    out = []
    for code, gross in sorted(groups.items()):
        rate = cfg["vat_codes"].get(code, {}).get("rate")
        if rate is None:
            out.append({"code": code, "rate": None, "gross": gross, "net": None, "vat": None})
            continue
        net = round(gross / (1 + rate / 100), 2)
        out.append({"code": code, "rate": rate, "gross": round(gross, 2), "net": net, "vat": round(gross - net, 2)})
    return out


def check(receipt: Receipt, cfg: dict | None = None) -> list[dict]:
    cfg = cfg or country.load()
    results = []

    def add(id_, ok, message):
        results.append({"id": id_, "ok": bool(ok), "message": message})

    items_sum = round(sum(i.amount for i in receipt.items), 2)
    expected = round(items_sum + receipt.rounding, 2)
    add("items_sum_total", abs(expected - receipt.total) <= TOL,
        f"Line items {items_sum:g} + rounding {receipt.rounding:g} = {expected:g}; printed total {receipt.total:g}")

    step = cfg.get("cash_rounding_to")
    if step and receipt.rounding:
        add("rounding_size", abs(receipt.rounding) < step,
            f"Cash rounding {receipt.rounding:g} must be smaller than {step}")

    known = set(cfg["vat_codes"])
    unknown = sorted({i.vat_code.upper() for i in receipt.items} - known)
    add("vat_codes_known", not unknown,
        "All VAT codes are valid" if not unknown else f"Unknown VAT code(s): {', '.join(unknown)}")

    if receipt.vat_summary:
        split = {v["code"]: v["gross"] for v in vat_split(receipt, cfg)}
        bad = []
        for line in receipt.vat_summary:
            mine = split.get(line.code.upper(), 0)
            if abs(mine - line.gross) > TOL:
                bad.append(f"{line.code}: items {mine:g} vs summary {line.gross:g}")
        add("vat_summary_matches", not bad,
            "VAT summary matches the line items" if not bad else "; ".join(bad))

    try:
        d = date.fromisoformat(receipt.date)
        add("date_valid", date(2000, 1, 1) <= d <= date.today(), f"Date {receipt.date}")
    except ValueError:
        add("date_valid", False, f"Date '{receipt.date}' is not YYYY-MM-DD")

    add("category_known", receipt.category in cfg["categories"], f"Category '{receipt.category}'")

    pattern = cfg.get("tax_number_regex")
    if receipt.tax_number and pattern:
        add("tax_number_format", bool(re.fullmatch(pattern, receipt.tax_number.strip())),
            f"Tax number '{receipt.tax_number}'")

    return results


def passed(results: list[dict]) -> bool:
    return all(r["ok"] for r in results)
