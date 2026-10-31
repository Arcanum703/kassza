"""Ordinary code that checks the model. The model reads the receipt; code does the maths.

Two receipt styles are handled:
- shop till receipts: a VAT letter (A/B/C...) after each line amount
- restaurant bills: no per-line letter, but a printed VAT table (rate, net, VAT, gross)

Every check returns a dict {id, ok, message}. A receipt is accepted only if all pass.
"""
import re
from datetime import date

from . import country
from .schema import Receipt, VatLine

TOL = 1.0  # HUF: per-line rounding on printed receipts


def _rate(line: VatLine, cfg: dict) -> float | None:
    if line.rate is not None:
        return line.rate
    if line.code:
        return cfg["vat_codes"].get(line.code.upper(), {}).get("rate")
    return None


def drop_table_total(receipt: Receipt) -> Receipt:
    """Remove a VAT-table row with no rate that is just the sum of the other rows.

    Small models often copy the table's own "Összesen" line as an extra row. That's a
    structural slip, not a misread number, so code fixes it instead of asking again.
    """
    rows = receipt.vat_summary
    rest = [l for l in rows if l.rate is not None or l.code]
    totals = [l for l in rows if l.rate is None and not l.code]
    if len(totals) == 1 and rest and abs(totals[0].gross - sum(l.gross for l in rest)) <= TOL * len(rest):
        return receipt.model_copy(update={"vat_summary": rest})
    return receipt


def vat_split(receipt: Receipt, cfg: dict | None = None) -> list[dict]:
    """Net / VAT per rate, computed by code from gross amounts (never taken from the model).

    Uses the printed VAT table if there is one, otherwise groups line items by VAT letter.
    """
    cfg = cfg or country.load()
    groups: list[tuple[str, float | None, float]] = []
    if receipt.vat_summary:
        for line in receipt.vat_summary:
            rate = _rate(line, cfg)
            groups.append((line.code or (f"{rate:g}%" if rate is not None else "?"), rate, line.gross))
    else:
        by_code: dict[str, float] = {}
        for it in receipt.items:
            code = (it.vat_code or "?").upper()
            by_code[code] = by_code.get(code, 0) + it.amount
        for code, gross in sorted(by_code.items()):
            groups.append((code, cfg["vat_codes"].get(code, {}).get("rate"), gross))
    out = []
    for code, rate, gross in groups:
        if rate is None:
            out.append({"code": code, "rate": None, "gross": round(gross, 2), "net": None, "vat": None})
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

    codes = {i.vat_code.upper() for i in receipt.items if i.vat_code}
    unknown = sorted(codes - set(cfg["vat_codes"]))
    if codes:
        add("vat_codes_known", not unknown,
            "All VAT letters are valid" if not unknown else f"Unknown VAT letter(s): {', '.join(unknown)}")

    if receipt.vat_summary:
        valid_rates = {v["rate"] for v in cfg["vat_codes"].values()}
        rate_bad, math_bad = [], []
        for line in receipt.vat_summary:
            rate = _rate(line, cfg)
            label = line.code or (f"{rate:g}%" if rate is not None else "?")
            if rate not in valid_rates:
                rate_bad.append(f"{label}: rate {rate}")
                continue
            if line.net is not None and line.vat is not None:
                if abs(line.net + line.vat - line.gross) > TOL:
                    math_bad.append(f"{label}: net {line.net:g} + VAT {line.vat:g} ≠ gross {line.gross:g}")
                elif abs(line.net * rate / 100 - line.vat) > TOL + 0.5:
                    math_bad.append(f"{label}: {rate:g}% of {line.net:g} is {line.net * rate / 100:.0f}, printed VAT {line.vat:g}")
        add("vat_rates_valid", not rate_bad,
            "VAT rates are legal Hungarian rates" if not rate_bad else "Unknown VAT rate: " + "; ".join(rate_bad))
        if any(l.net is not None and l.vat is not None for l in receipt.vat_summary):
            add("vat_table_math", not math_bad,
                "Each VAT row: net + VAT = gross, and VAT = net × rate" if not math_bad else "; ".join(math_bad))

        table_gross = round(sum(l.gross for l in receipt.vat_summary), 2)
        add("vat_table_total", abs(table_gross - items_sum) <= TOL * len(receipt.vat_summary),
            f"VAT table gross {table_gross:g} vs line items {items_sum:g}")

        if codes and all(l.code for l in receipt.vat_summary):
            per_code: dict[str, float] = {}
            for it in receipt.items:
                if it.vat_code:
                    per_code[it.vat_code.upper()] = per_code.get(it.vat_code.upper(), 0) + it.amount
            bad = [f"{l.code}: items {per_code.get(l.code.upper(), 0):g} vs table {l.gross:g}"
                   for l in receipt.vat_summary if abs(per_code.get(l.code.upper(), 0) - l.gross) > TOL]
            add("vat_letters_match_table", not bad,
                "Items grouped by VAT letter match the VAT table" if not bad else "; ".join(bad))

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
