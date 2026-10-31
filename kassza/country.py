"""Country configuration: VAT codes, categories and receipt hints.

Add a country by dropping a `countries/<code>.json` file next to `hu.json`.
"""
import json
import os
from functools import lru_cache
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


@lru_cache
def load(code: str | None = None) -> dict:
    code = (code or os.getenv("KASSZA_COUNTRY", "hu")).lower()
    return json.loads((ROOT / "countries" / f"{code}.json").read_text(encoding="utf-8"))
