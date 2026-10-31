"""What the model must return for a receipt. Pydantic rejects anything else."""
from pydantic import BaseModel, Field


class Item(BaseModel):
    name: str
    amount: float = Field(description="Gross line amount as printed, after any discount")
    vat_code: str = Field(description="VAT letter printed next to the amount, e.g. A/B/C")


class VatLine(BaseModel):
    code: str
    gross: float = Field(description="Gross total printed for this VAT code in the summary")


class Receipt(BaseModel):
    vendor: str
    tax_number: str | None = None
    date: str = Field(description="YYYY-MM-DD")
    currency: str = "HUF"
    items: list[Item]
    vat_summary: list[VatLine] = []
    rounding: float = 0
    total: float = Field(description="Amount paid, as printed")
    category: str
