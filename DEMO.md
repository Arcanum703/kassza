# Kassza: 2-minute demo

## Before going on stage (5 min)
1. Run `python app.py` and open http://localhost:8000.
2. Click **Clear** on the ledger. Click **Private · on-device** once, so the local model loads (that takes about 80s the first time), then switch back to **Cloud · Gemini API**.
3. Have the paper restaurant receipt in your hand. The same photo is in `samples/`.
4. Pre-cache every demo input: scan the receipt in both modes, click **Load demo statement** and click **Get advice** once. If wifi or the API dies, set `KASSZA_REPLAY=1` and restart; every response then comes from `cache/`. The advice prompt depends on what's in the ledger, so rehearse **from a cleared ledger in exactly this order**: receipt, demo statement, advice.
5. Open a second tab on the GitHub repo.

## Script

**0:00–0:30 · The hook**
> "This is a real dinner bill from Budapest. No item has a VAT letter, just this ÁFA table at the bottom."

Drop the photo in. It comes back in about 10s.
> "Gemma 4 read every line, and the VAT table at 5% and 27%. But I don't trust a model with money, so ordinary code checked it. The items add up to 28,127. Net plus VAT equals gross on each row. 5% of 22,450 is the 1,123 that's printed. Everything is green."

**0:30–0:55 · It catches its own mistakes**
Scroll through the green checks.
> "If the model misreads a digit, these go red. Gemma is shown the exact errors and looks again. A bad reading never reaches your ledger."

**0:55–1:25 · Advice you can trust**
Click **Load demo statement**, then **Get advice**.
> "Two months of bank history. Code computes the facts. Gemma writes the advice, but it may only quote numbers from those facts."

Click a fact chip (e.g. F23) and the fact it cites is highlighted.
> "Eating out went from 31 to 101 thousand forints. Every number here is checked against my own data. A suggestion with a made-up number is thrown out and shown in red."

**1:25–1:50 · The reason it has to be open**
Click **Private · on-device**. Turn wifi off; the header shows ✈ offline.
> "Receipts and bank history are the most private data you have. A closed model means sending them to someone's cloud. Gemma's open weights mean the same app runs on this laptop with the network off."

Scan the receipt again; it's cached from the rehearsal.

**1:50–2:00 · Fork it**
Show the repo tab.
> "MIT licence. Adding your country is one JSON file of VAT rates. The CSV export goes into Actual Budget or Firefly III. Kassza."

## If something breaks
| Problem | Do this |
|---|---|
| API 503 or slow | `KASSZA_REPLAY=1`, restart, carry on. Everything you rehearsed is cached. |
| A check goes red live | "That's the point: it caught the model." Show the retry note. |
| Local model is slow | Talk through the advice while it runs (about 45s when warm), or use the cached result. |
| Laptop dies | Play the backup video. |
