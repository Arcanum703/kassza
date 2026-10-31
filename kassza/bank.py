"""Bank CSV -> transactions. Amounts are parsed by code; Gemma only names categories.

Handles Revolut exports and generic CSVs with date / description / amount columns.
"""
import csv
import io
import re

from . import country, db, llm

DATE_COLS = ("completed date", "started date", "date", "dátum", "könyvelés dátuma", "booking date")
DESC_COLS = ("description", "közlemény", "partner", "merchant", "megnevezés", "details")
AMOUNT_COLS = ("amount", "összeg", "value")


def _col(header: list[str], names) -> int | None:
    low = [h.strip().lower() for h in header]
    for n in names:
        if n in low:
            return low.index(n)
    return None


def _num(s: str) -> float:
    s = s.replace(" ", "").replace(" ", "")
    if re.fullmatch(r"-?\d{1,3}(\.\d{3})*(,\d+)?", s):  # 1.234,56
        s = s.replace(".", "").replace(",", ".")
    return float(s.replace(",", ""))


def parse(text: str) -> list[dict]:
    dialect = csv.Sniffer().sniff(text[:2000], delimiters=",;\t")
    rows = list(csv.reader(io.StringIO(text), dialect))
    header, body = rows[0], rows[1:]
    di, de, am = _col(header, DATE_COLS), _col(header, DESC_COLS), _col(header, AMOUNT_COLS)
    if None in (di, de, am):
        raise ValueError(f"Could not find date/description/amount columns in: {header}")
    cur = _col(header, ("currency", "pénznem"))
    state = _col(header, ("state",))
    out = []
    for r in body:
        if len(r) <= max(di, de, am) or not r[am].strip():
            continue
        if state is not None and r[state].strip().upper() not in ("COMPLETED", ""):
            continue
        out.append({"date": r[di].strip()[:10].replace(".", "-"), "merchant": r[de].strip(),
                    "amount": _num(r[am]), "currency": r[cur].strip() if cur is not None else "HUF",
                    "raw": dict(zip(header, r))})
    return out


CAT_PROMPT = """Assign a spending category to each bank transaction description.
Allowed categories: {categories}, plus "income" for money received and "transfer" for own-account moves, top-ups and savings.
Return ONLY a JSON object mapping each description exactly as given to one category.
Descriptions (with a sample signed amount):
{lines}"""


def categorize(rows: list[dict]) -> dict[str, str]:
    cfg = country.load()
    allowed = set(cfg["categories"]) | {"income", "transfer"}
    sample = {}
    for r in rows:
        sample.setdefault(r["merchant"], r["amount"])
    lines = "\n".join(f"- {m} ({a:g})" for m, a in sample.items())
    out = llm.generate(CAT_PROMPT.format(categories=", ".join(cfg["categories"]), lines=lines))
    mapping = llm.parse_json(out["text"])
    return {m: (mapping.get(m) if mapping.get(m) in allowed else "other") for m in sample}


def import_csv(text: str) -> dict:
    rows = parse(text)
    cats = categorize(rows)
    added = 0
    for r in rows:
        key = f"bank|{r['date']}|{r['merchant']}|{r['amount']}"
        if db.add("bank", r["date"], r["merchant"], r["amount"], r["currency"], cats[r["merchant"]],
                  r["raw"], key):
            added += 1
    return {"parsed": len(rows), "added": added, "categories": cats}
