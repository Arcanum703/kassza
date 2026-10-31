"""Writes samples/demo-bank.csv: a synthetic two-month Revolut-style export for the demo."""
import csv, random
random.seed(7)
rows = []
def add(day, desc, amt, typ="CARD_PAYMENT"):
    rows.append([typ, "Current", f"{day} 12:00:00", f"{day} 12:05:00", desc, f"{amt:.2f}", "0.00", "HUF", "COMPLETED", ""])
for m in ("2026-09", "2026-10"):
    add(f"{m}-01", "Salary Acme Kft", 520000, "TOPUP")
    add(f"{m}-02", "Rent transfer", -210000, "TRANSFER")
    add(f"{m}-03", "Spotify", -1990)
    add(f"{m}-04", "Netflix", -4490)
    add(f"{m}-05", "YouTube Premium", -2490)
    add(f"{m}-06", "Fitness Gym Budapest", -14900)
    add(f"{m}-07", "BKK Budapest pass", -8950)
    add(f"{m}-10", "Telekom mobile", -6990)
    for i in range(9 if m.endswith("09") else 11):
        add(f"{m}-{8 + i * 2:02d}", random.choice(["Lidl", "Aldi", "Spar", "Tesco"]), -random.randint(3500, 14000))
    for i in range(5 if m.endswith("09") else 12):
        add(f"{m}-{9 + i * 1:02d}", random.choice(["Wolt", "Foodora", "Bolt Food"]), -random.randint(3200, 7800))
    for i in range(3):
        add(f"{m}-{12 + i * 5:02d}", random.choice(["Costa Coffee", "Starbucks", "Espresso Embassy"]), -random.randint(1200, 2600))
    add(f"{m}-20", "Bolt ride", -random.randint(2500, 5200))
    add(f"{m}-22", "dm drogerie", -random.randint(3000, 9000))
rows.sort(key=lambda r: r[2])
with open("samples/demo-bank.csv", "w", newline="", encoding="utf-8") as f:
    w = csv.writer(f)
    w.writerow(["Type", "Product", "Started Date", "Completed Date", "Description", "Amount", "Fee", "Currency", "State", "Balance"])
    w.writerows(rows)
print(len(rows), "rows")
