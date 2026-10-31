from kassza import validate
from kassza.schema import Receipt


def make(**kw):
    base = dict(vendor="Lidl", date="2026-10-30", category="groceries", total=1500,
                items=[{"name": "Kenyér", "amount": 500, "vat_code": "A"},
                       {"name": "Mosópor", "amount": 1000, "vat_code": "C"}])
    base.update(kw)
    return Receipt.model_validate(base)


def ids_failed(r):
    return {c["id"] for c in validate.check(r) if not c["ok"]}


def test_clean_receipt_passes():
    assert ids_failed(make()) == set()


def test_total_mismatch_is_caught():
    assert "items_sum_total" in ids_failed(make(total=1600))


def test_cash_rounding_counts():
    assert ids_failed(make(total=1500, rounding=0)) == set()
    r = make(items=[{"name": "Tej", "amount": 452, "vat_code": "B"}], total=450, rounding=-2)
    assert ids_failed(r) == set()


def test_vat_split_is_computed_by_code():
    split = {v["code"]: v for v in validate.vat_split(make())}
    assert split["A"]["net"] == round(500 / 1.05, 2)
    assert split["C"]["vat"] == round(1000 - 1000 / 1.27, 2)


def test_vat_summary_mismatch_is_caught():
    r = make(vat_summary=[{"code": "A", "gross": 500}, {"code": "C", "gross": 900}])
    assert "vat_letters_match_table" in ids_failed(r)


def test_unknown_vat_code_and_category():
    r = make(items=[{"name": "x", "amount": 1500, "vat_code": "Z"}], category="crypto")
    assert {"vat_codes_known", "category_known"} <= ids_failed(r)


def test_future_date_rejected():
    assert "date_valid" in ids_failed(make(date="2099-01-01"))


def restaurant(**kw):
    """Real restaurant bill: no per-line VAT letter, printed VAT table instead."""
    base = dict(vendor="Étterem", date="2026-10-18", category="eating_out", total=28127,
                items=[{"name": "Irish Stout", "amount": 4140}, {"name": "Gulyásleves", "amount": 2980},
                       {"name": "Sertésszűz", "amount": 11600}, {"name": "Marhapörkölt", "amount": 5400},
                       {"name": "Somlói", "amount": 1450}, {"name": "Szervizdíj", "amount": 2557}],
                vat_summary=[{"rate": 5, "net": 22450, "vat": 1123, "gross": 23573},
                             {"rate": 27, "net": 3586, "vat": 968, "gross": 4554}])
    base.update(kw)
    return Receipt.model_validate(base)


def test_restaurant_bill_passes():
    assert ids_failed(restaurant()) == set()


def test_restaurant_vat_misread_is_caught():
    r = restaurant(vat_summary=[{"rate": 5, "net": 22450, "vat": 1123, "gross": 23573},
                                {"rate": 27, "net": 3586, "vat": 698, "gross": 4554}])
    assert "vat_table_math" in ids_failed(r)


def test_illegal_vat_rate_is_caught():
    r = restaurant(vat_summary=[{"rate": 5, "gross": 23573}, {"rate": 25, "gross": 4554}])
    assert "vat_rates_valid" in ids_failed(r)


def test_restaurant_split_uses_table():
    split = validate.vat_split(restaurant())
    assert [v["rate"] for v in split] == [5, 27]
    assert split[1]["vat"] == round(4554 - 4554 / 1.27, 2)
