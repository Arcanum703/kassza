"""Spending facts computed by code, advice written by Gemma, numbers checked by code.

The model never sees raw rows and never does arithmetic: it gets a numbered list of facts
and may only quote numbers that appear in them. Any suggestion with an unknown number or
an unknown fact id is rejected (and shown as rejected, not silently dropped).
"""
import re
from collections import defaultdict

from . import db, llm

SKIP = {"income", "transfer"}


def facts(rows: list[dict]) -> list[dict]:
    spend = [r for r in rows if r["amount"] < 0 and r["category"] not in SKIP]
    if not spend:
        return []
    months = sorted({r["date"][:7] for r in spend})
    n_months = len(months)
    out = []

    def fact(text, **values):
        out.append({"id": f"F{len(out) + 1}", "text": text, "values": values})

    total = -sum(r["amount"] for r in spend)
    fact(f"Total spending {round(total)} HUF over {n_months} month(s) ({months[0]} to {months[-1]}), "
         f"{round(total / n_months)} HUF per month on average.",
         total=round(total), per_month=round(total / n_months))

    by_cat = defaultdict(float)
    for r in spend:
        by_cat[r["category"]] -= r["amount"]
    for cat, amt in sorted(by_cat.items(), key=lambda kv: -kv[1]):
        share = round(100 * amt / total)
        fact(f"{cat}: {round(amt)} HUF total, {round(amt / n_months)} HUF per month, {share}% of spending.",
             total=round(amt), per_month=round(amt / n_months), share=share)

    by_merchant_month = defaultdict(lambda: defaultdict(list))
    for r in spend:
        by_merchant_month[r["merchant"]][r["date"][:7]].append(-r["amount"])
    for merchant, per_month in by_merchant_month.items():
        if len(per_month) < 2 or any(len(v) != 1 for v in per_month.values()):
            continue  # subscriptions charge once a month
        monthly = [sum(v) for v in per_month.values()]
        lo, hi = min(monthly), max(monthly)
        if hi <= lo * 1.15:  # same amount every month -> subscription-like
            avg = round(sum(monthly) / len(monthly))
            fact(f"Recurring: {merchant} charges about {avg} HUF every month "
                 f"({len(monthly)} months seen), {avg * 12} HUF per year.",
                 per_month=avg, per_year=avg * 12, months=len(monthly))

    merchants = defaultdict(lambda: [0.0, 0])
    for r in spend:
        merchants[r["merchant"]][0] -= r["amount"]
        merchants[r["merchant"]][1] += 1
    for m, (amt, count) in sorted(merchants.items(), key=lambda kv: -kv[1][0])[:5]:
        fact(f"Top merchant {m}: {round(amt)} HUF across {count} payments, {round(amt / count)} HUF each on average.",
             total=round(amt), count=count, avg=round(amt / count))

    if n_months >= 2:
        last, prev = months[-1], months[-2]
        for cat in by_cat:
            a = -sum(r["amount"] for r in spend if r["category"] == cat and r["date"].startswith(last))
            b = -sum(r["amount"] for r in spend if r["category"] == cat and r["date"].startswith(prev))
            if b > 0 and abs(a - b) / b >= 0.25 and abs(a - b) >= 3000:
                fact(f"{cat} went from {round(b)} HUF in {prev} to {round(a)} HUF in {last} "
                     f"({'+' if a > b else '-'}{round(abs(a - b))} HUF).",
                     before=round(b), after=round(a), change=round(abs(a - b)))
    return out


PROMPT = """You are a careful personal-finance coach. Below are facts about one person's spending,
computed exactly by software. Give 3 concrete suggestions for what to cut or change next month.

Hard rules:
- Use ONLY numbers that appear in the facts, copied exactly. Do not calculate new numbers.
- Every suggestion must cite the fact ids it relies on.
- Be specific: name the merchant or subscription to cancel or cap, not "review your spending".
- The 3 suggestions must be about 3 different categories. Start with the biggest month-over-month increase, if there is one.
- In "detail", quote the relevant amounts from the facts so the reader sees why.
- "monthly_saving" must be a per-month number copied from a cited fact (e.g. a recurring charge you suggest cancelling), or 0.

Facts:
{facts}

Return ONLY JSON: {{"suggestions": [{{"title": str, "detail": str, "fact_ids": [str], "monthly_saving": number}}]}}"""

NUM = re.compile(r"\d[\d\s.,]*\d|\d")


def _numbers(text: str) -> list[int]:
    found = []
    for m in NUM.findall(text):
        digits = re.sub(r"[\s.,]", "", m)
        if digits:
            found.append(int(digits))
    return found


def ground(suggestion: dict, fact_list: list[dict]) -> list[str]:
    """Returns the problems with one suggestion; empty list = grounded."""
    by_id = {f["id"]: f for f in fact_list}
    problems = [f"unknown fact id {i}" for i in suggestion.get("fact_ids", []) if i not in by_id]
    if not suggestion.get("fact_ids"):
        problems.append("cites no facts")
    allowed = set()
    for f in fact_list:
        allowed.update(_numbers(f["text"]))
    text = f"{suggestion.get('title', '')} {suggestion.get('detail', '')}"
    for n in _numbers(text):
        if n > 12 and n not in allowed and not 2000 <= n <= 2100:
            problems.append(f"number {n} is not in the facts")
    saving = suggestion.get("monthly_saving") or 0
    if saving and round(float(saving)) not in allowed:
        problems.append(f"monthly_saving {saving} is not in the facts")
    return problems


def advise(owner: str) -> dict:
    fact_list = facts(db.all_tx(owner))
    if not fact_list:
        return {"facts": [], "suggestions": [], "rejected": []}
    prompt = PROMPT.format(facts="\n".join(f"{f['id']}: {f['text']}" for f in fact_list))
    out = llm.generate(prompt)
    suggestions = llm.parse_json(out["text"]).get("suggestions", [])
    good, bad = [], []
    for s in suggestions:
        (bad if (p := ground(s, fact_list)) else good).append({**s, "problems": p})
    if bad and len(good) < 3:
        retry = prompt + "\n\nThese suggestions were rejected by the number checker:\n" + "\n".join(
            f"- {s['title']}: {'; '.join(s['problems'])}" for s in bad) + "\nReturn 3 corrected suggestions."
        again = llm.parse_json(llm.generate(retry)["text"]).get("suggestions", [])
        fixed = [s for s in again if not ground(s, fact_list)]
        good = (good + [{**s, "problems": []} for s in fixed])[:3]
    return {"facts": fact_list, "suggestions": good[:3], "rejected": bad,
            "backend": out["backend"], "model": out["model"]}
