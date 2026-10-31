"""Kassza web app: `python app.py`, then open http://localhost:8000"""
import csv
import io
import os
import threading

import uvicorn
from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.responses import FileResponse, PlainTextResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

import kassza  # noqa: F401  (loads .env)
from kassza import bank, db, insights, llm, receipt

ROOT = os.path.dirname(os.path.abspath(__file__))
app = FastAPI(title="Kassza")
app.mount("/static", StaticFiles(directory=os.path.join(ROOT, "static")), name="static")


@app.get("/")
def index():
    return FileResponse(os.path.join(ROOT, "static", "index.html"))


class Backend(BaseModel):
    backend: str


@app.get("/api/backend")
def get_backend():
    return {"backend": llm.get_backend(), "model": llm.model_name(),
            "replay": os.getenv("KASSZA_REPLAY") == "1"}


@app.post("/api/backend")
def set_backend(b: Backend):
    try:
        llm.set_backend(b.backend)
        if b.backend == "ollama":
            threading.Thread(target=llm.warm_ollama, daemon=True).start()
    except ValueError:
        raise HTTPException(400, "backend must be gemini or ollama")
    return get_backend()


@app.post("/api/scan")
async def scan(file: UploadFile = File(...)):
    image = await file.read()
    try:
        result = receipt.scan(image, file.content_type or "image/jpeg")
    except Exception as e:  # surface model/network errors to the UI instead of a 500 page
        raise HTTPException(502, f"{type(e).__name__}: {e}")
    r = result["receipt"]
    if r and result["ok"]:
        result["tx_id"] = db.add("receipt", r["date"], r["vendor"], -r["total"], r["currency"],
                                 r["category"], r, f"receipt|{r['date']}|{r['vendor']}|{r['total']}")
    return result


@app.post("/api/import")
async def import_csv(file: UploadFile = File(...)):
    text = (await file.read()).decode("utf-8-sig")
    try:
        return bank.import_csv(text)
    except Exception as e:
        raise HTTPException(502, f"{type(e).__name__}: {e}")


@app.get("/api/ledger")
def ledger():
    return db.all_tx()


@app.delete("/api/ledger")
def clear():
    db.clear()
    return {"ok": True}


@app.get("/api/insights")
def get_insights():
    try:
        return insights.advise()
    except Exception as e:
        raise HTTPException(502, f"{type(e).__name__}: {e}")


@app.get("/api/export.csv", response_class=PlainTextResponse)
def export():
    """Columns match the CSV importers of Actual Budget and Firefly III (date, payee, category, amount)."""
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["date", "payee", "category", "amount", "currency", "source"])
    for t in db.all_tx():
        w.writerow([t["date"], t["merchant"], t["category"], t["amount"], t["currency"], t["source"]])
    return PlainTextResponse(buf.getvalue(), media_type="text/csv",
                             headers={"Content-Disposition": "attachment; filename=kassza-ledger.csv"})


if __name__ == "__main__":
    uvicorn.run(app, host="127.0.0.1", port=int(os.getenv("PORT", "8000")))
