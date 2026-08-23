"""An invoice billed nothing for everything, and reported success.

A sweep called create_invoice with two real line items:

    [{"description": "Google Ads",   "qty": 2, "price": 969501.63},
     {"description": "Facebook Ads", "qty": 1, "price": 564115.51}]

and got a complete, correctly formatted, fully styled invoice:

    Description    Quantity  Unit Price  Total
    Google Ads     0         0           =B7*C7
    Facebook Ads   0         0           =B8*C8
                             Subtotal    =SUM(D7:D8)
                             Tax (8.5%)  =D10*0.085
                             Total (USD) =D10+D11

    success: True, subtotal: 0.0

The item reader was `item.get("quantity", 0)` and `item.get("unit_price", 0.0)`,
so any other spelling silently became zero. The descriptions came through, which
makes the document look more legitimate, not less. `items` is a bare `list` in
the schema, and the key names appeared in exactly one place -- the error hint
for an *empty* list -- which a caller sending two real items never sees.

Same shape as the tax_rate defect on this tool: a number nobody documented,
accepted without complaint, and billed. Zeroing money in silence is worse than
refusing, so the common spellings are now honoured and anything still unpriced
is named.
"""

from __future__ import annotations

from pathlib import Path

import openpyxl
import pytest

from xlsx_new.engine import create_invoice  # type: ignore[reportMissingImports]

REAL_ITEMS_CANONICAL = [
    {"description": "Google Ads", "quantity": 2, "unit_price": 969501.63},
    {"description": "Facebook Ads", "quantity": 1, "unit_price": 564115.51},
]
REAL_SUBTOTAL = 2503118.77


def invoice_rows(path: str, count: int) -> list[tuple]:
    ws = openpyxl.load_workbook(path).active
    assert ws is not None
    return list(ws.iter_rows(min_row=7, max_row=6 + count, values_only=True))


@pytest.fixture()
def out_path(tmp_path: Path) -> str:
    return str(tmp_path / "invoice.xlsx")


class TestTheSweepsCall:
    """qty/price -- the spelling that produced a zero invoice."""

    ITEMS = [
        {"description": "Google Ads", "qty": 2, "price": 969501.63},
        {"description": "Facebook Ads", "qty": 1, "price": 564115.51},
    ]

    def test_it_no_longer_bills_zero(self, out_path: str):
        r = create_invoice(out_path, "Acme", "Client", "INV-1", self.ITEMS, tax_rate=0.085, open_after=False)
        assert r["success"] is True, r.get("error")
        assert r["subtotal"] == pytest.approx(REAL_SUBTOTAL)

    def test_the_quantities_reach_the_sheet(self, out_path: str):
        create_invoice(out_path, "Acme", "Client", "INV-1", self.ITEMS, tax_rate=0.085, open_after=False)
        assert [row[1] for row in invoice_rows(out_path, 2)] == [2, 1]

    def test_the_prices_reach_the_sheet(self, out_path: str):
        create_invoice(out_path, "Acme", "Client", "INV-1", self.ITEMS, tax_rate=0.085, open_after=False)
        assert [row[2] for row in invoice_rows(out_path, 2)] == [969501.63, 564115.51]


class TestOtherSpellingsAlsoWork:
    @pytest.mark.parametrize(
        "item",
        [
            {"description": "A", "quantity": 2, "unit_price": 10.0},
            {"desc": "A", "qty": 2, "rate": 10.0},
            {"item": "A", "units": 2, "cost": 10.0},
            {"name": "A", "count": 2, "unitprice": 10.0},
            {"service": "A", "hours": 2, "unit_cost": 10.0},
        ],
    )
    def test_a_row_of_twenty_is_produced(self, out_path: str, item: dict):
        r = create_invoice(out_path, "Acme", "Client", "INV-1", [item], open_after=False)
        assert r["success"] is True, (item, r.get("error"))
        assert r["subtotal"] == pytest.approx(20.0), item

    def test_the_description_is_read_under_its_aliases(self, out_path: str):
        create_invoice(out_path, "Acme", "C", "INV-1", [{"item": "Google Ads", "qty": 1, "price": 5}], open_after=False)
        assert invoice_rows(out_path, 1)[0][0] == "Google Ads"

    def test_key_case_and_spacing_do_not_matter(self, out_path: str):
        r = create_invoice(
            out_path, "Acme", "C", "INV-1", [{"Description": "A", "Unit Price": 10.0, "QTY": 2}], open_after=False
        )
        assert r["success"] is True, r.get("error")
        assert r["subtotal"] == pytest.approx(20.0)


class TestAnUnpricedItemIsRefused:
    def test_a_completely_unrecognised_shape_fails(self, out_path: str):
        r = create_invoice(out_path, "Acme", "C", "INV-1", [{"description": "A", "spend": 5.0}], open_after=False)
        assert r["success"] is False

    def test_the_error_names_the_keys_that_were_sent(self, out_path: str):
        r = create_invoice(out_path, "Acme", "C", "INV-1", [{"description": "A", "spend": 5.0}], open_after=False)
        assert "spend" in r["error"], r["error"]

    def test_the_hint_names_the_keys_that_work(self, out_path: str):
        r = create_invoice(out_path, "Acme", "C", "INV-1", [{"description": "A", "spend": 5.0}], open_after=False)
        assert "quantity" in r["hint"] and "unit_price" in r["hint"], r["hint"]

    def test_a_non_object_item_is_refused_not_charged_zero(self, out_path: str):
        r = create_invoice(out_path, "Acme", "C", "INV-1", ["Google Ads"], open_after=False)
        assert r["success"] is False
        assert "not an object" in r["error"], r["error"]

    def test_a_non_numeric_price_is_refused(self, out_path: str):
        r = create_invoice(
            out_path,
            "Acme",
            "C",
            "INV-1",
            [{"description": "A", "quantity": 1, "unit_price": "free"}],
            open_after=False,
        )
        assert r["success"] is False

    def test_nothing_is_written_when_it_refuses(self, out_path: str):
        create_invoice(out_path, "Acme", "C", "INV-1", [{"description": "A", "spend": 5.0}], open_after=False)
        assert not Path(out_path).exists()

    def test_one_bad_item_among_good_ones_still_refuses(self, out_path: str):
        r = create_invoice(
            out_path,
            "Acme",
            "C",
            "INV-1",
            [*REAL_ITEMS_CANONICAL, {"description": "Mystery", "spend": 1.0}],
            open_after=False,
        )
        assert r["success"] is False
        assert "1 of 3" in r["error"], r["error"]


class TestTheOrdinaryInvoiceIsUnchanged:
    def test_canonical_keys_still_produce_the_same_sheet(self, out_path: str):
        r = create_invoice(out_path, "Acme", "C", "INV-1", REAL_ITEMS_CANONICAL, tax_rate=0.085, open_after=False)
        assert r["success"] is True, r.get("error")
        rows = invoice_rows(out_path, 2)
        assert [row[0] for row in rows] == ["Google Ads", "Facebook Ads"]
        assert [row[3] for row in rows] == ["=B7*C7", "=B8*C8"]

    def test_the_tax_rate_guard_still_fires(self, out_path: str):
        r = create_invoice(out_path, "Acme", "C", "INV-1", REAL_ITEMS_CANONICAL, tax_rate=8.5, open_after=False)
        assert r["success"] is False
        assert "fraction" in r["error"], r["error"]

    def test_an_empty_list_is_still_refused_first(self, out_path: str):
        r = create_invoice(out_path, "Acme", "C", "INV-1", [], open_after=False)
        assert r["success"] is False
        assert "non-empty" in r["error"], r["error"]
