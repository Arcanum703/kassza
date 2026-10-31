"""Receipt photo -> validated ledger entry.

Gemma reads the photo into JSON. Pydantic checks the shape, validate.py checks the maths.
If either fails, Gemma gets one retry with the exact errors.
"""
import json

from pydantic import ValidationError

from . import country, llm, validate
from .schema import Receipt

PROMPT = """You are reading a photo of a till receipt. Country config:
{hints}
VAT codes: {codes}
Allowed categories: {categories}

Return ONLY a JSON object with exactly these keys:
{{"vendor": str, "tax_number": str|null, "date": "YYYY-MM-DD", "currency": "{currency}",
 "items": [{{"name": str, "amount": number, "vat_code": str|null}}],
 "vat_summary": [{{"code": str|null, "rate": number|null, "net": number|null, "vat": number|null, "gross": number}}],
 "rounding": number, "total": number, "category": str}}

Rules:
- Copy every purchased line. "amount" is the line's gross amount as printed, after line discounts (discounts are negative lines).
- "vat_code" is the letter printed next to that amount, or null if the receipt prints none (common on restaurant bills).
- Service charge ("Szervizdíj") is a line item.
- "vat_summary" copies the printed VAT breakdown ("ÁFA bontás", per-letter totals) row by row: letter if printed, rate in %, net, VAT, gross. Use null for columns not printed. [] if there is no breakdown.
- "rounding" is the cash rounding line ("Kerekítés"), else 0. "total" is the amount paid.
- Item names: keep the original language. Do not invent lines or numbers you cannot read.
- "category" must be one of the allowed categories, for the receipt as a whole."""

RETRY = """Your previous JSON for this same receipt failed these checks:
{errors}
Previous JSON:
{previous}
Look at the photo again, fix only what is wrong, and return the corrected JSON object only."""


def _prompt(cfg: dict) -> str:
    codes = ", ".join(f"{k}={v['rate']}%" for k, v in cfg["vat_codes"].items())
    return PROMPT.format(hints=cfg["receipt_hints"], codes=codes,
                         categories=", ".join(cfg["categories"]), currency=cfg["currency"])


def _attempt(prompt: str, image: bytes, mime: str):
    out = llm.generate(prompt, image, mime)
    try:
        receipt = Receipt.model_validate(llm.parse_json(out["text"]))
    except (ValueError, ValidationError) as e:
        return out, None, [{"id": "schema", "ok": False, "message": str(e)[:400]}]
    return out, receipt, validate.check(receipt)


def scan(image: bytes, mime: str = "image/jpeg") -> dict:
    cfg = country.load()
    prompt = _prompt(cfg)
    attempts = []
    out, receipt, checks = _attempt(prompt, image, mime)
    attempts.append({"seconds": out["seconds"], "cached": out["cached"], "checks": checks})
    if not validate.passed(checks):
        errors = "\n".join(f"- {c['message']}" for c in checks if not c["ok"])
        previous = receipt.model_dump_json() if receipt else out["text"][:2000]
        out, retry_receipt, retry_checks = _attempt(prompt + "\n\n" + RETRY.format(errors=errors, previous=previous),
                                                    image, mime)
        attempts.append({"seconds": out["seconds"], "cached": out["cached"], "checks": retry_checks})
        if retry_receipt is not None:
            receipt, checks = retry_receipt, retry_checks
    return {
        "receipt": json.loads(receipt.model_dump_json()) if receipt else None,
        "vat_split": validate.vat_split(receipt, cfg) if receipt else [],
        "checks": checks,
        "ok": receipt is not None and validate.passed(checks),
        "attempts": attempts,
        "backend": out["backend"],
        "model": out["model"],
    }
