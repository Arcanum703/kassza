"""Kassza web app: `python app.py`, then open http://localhost:8000"""
import csv
import io
import os
import threading

import uvicorn
from fastapi import FastAPI, File, Header, HTTPException, UploadFile
from fastapi.responses import FileResponse, PlainTextResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

import kassza  # noqa: F401  (loads .env)
from kassza import bank, db, insights, llm, receipt

ROOT = os.path.dirname(os.path.abspath(__file__))
app = FastAPI(title="Kassza")
app.mount("/static", StaticFiles(directory=os.path.join(ROOT, "static")), name="static")


def _err(e: Exception) -> str:
    """Error text for the browser, with the API key scrubbed out."""
    msg = f"{type(e).__name__}: {e}"
    key = (os.getenv("GEMINI_API_KEY") or "").strip().strip('"').strip("'")
    return msg.replace(key, "***") if key else msg


@app.get("/")
def index():
    return FileResponse(os.path.join(ROOT, "static", "index.html"))


class Backend(BaseModel):
    backend: str


@app.get("/api/backend")
def get_backend():
    return {"backend": llm.get_backend(), "model": llm.model_name(),
            "replay": os.getenv("KASSZA_REPLAY") == "1",
            "private_available": not os.getenv("VERCEL")}


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
async def scan(file: UploadFile = File(...), x_kassza_user: str = Header("")):
    image = await file.read()
    try:
        result = receipt.scan(image, file.content_type or "image/jpeg")
    except Exception as e:  # surface model/network errors to the UI instead of a 500 page
        raise HTTPException(502, _err(e))
    r = result["receipt"]
    if r and result["ok"]:
        r["vat_paid"] = round(sum(v["vat"] or 0 for v in result["vat_split"]))
        result["tx_id"] = db.add(x_kassza_user, "receipt", r["date"], r["vendor"], -r["total"], r["currency"],
                                 r["category"], r, f"receipt|{r['date']}|{r['vendor']}|{r['total']}")
    return result


@app.post("/api/import")
async def import_csv(file: UploadFile = File(...), x_kassza_user: str = Header("")):
    text = (await file.read()).decode("utf-8-sig")
    try:
        return bank.import_csv(text, x_kassza_user)
    except Exception as e:
        raise HTTPException(502, _err(e))


@app.get("/api/ledger")
def ledger(x_kassza_user: str = Header("")):
    return db.all_tx(x_kassza_user)


@app.delete("/api/ledger")
def clear(x_kassza_user: str = Header("")):
    db.clear(x_kassza_user)
    return {"ok": True}


@app.get("/api/insights")
def get_insights(x_kassza_user: str = Header("")):
    try:
        return insights.advise(x_kassza_user)
    except Exception as e:
        raise HTTPException(502, _err(e))


@app.get("/api/export.csv", response_class=PlainTextResponse)
def export(user: str = ""):
    """Columns match the CSV importers of Actual Budget and Firefly III (date, payee, category, amount)."""
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["date", "payee", "category", "amount", "currency", "source"])
    for t in db.all_tx(user):
        w.writerow([t["date"], t["merchant"], t["category"], t["amount"], t["currency"], t["source"]])
    return PlainTextResponse(buf.getvalue(), media_type="text/csv",
                             headers={"Content-Disposition": "attachment; filename=kassza-ledger.csv"})


if __name__ == "__main__":
    uvicorn.run(app, host="127.0.0.1", port=int(os.getenv("PORT", "8000")))
