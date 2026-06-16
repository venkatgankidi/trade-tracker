"""Unit tests for the wash-sale detection engine in ui/taxes_ui.py.

All tests exercise detect_wash_sales() and _parse_date() directly —
no database connection required.
"""

import datetime
import pytest
from ui.taxes_ui import detect_wash_sales, _parse_date, WASH_SALE_WINDOW_DAYS


# ---------------------------------------------------------------------------
# Helpers to build minimal test fixtures
# ---------------------------------------------------------------------------

def _make_pos(ticker, entry_date, exit_date, profit_loss, quantity=100):
    """Build a minimal closed-position dict."""
    return {
        "ticker": ticker,
        "entry_date": entry_date,
        "exit_date": exit_date,
        "entry_price": 50.0,
        "exit_price": 50.0 + profit_loss / quantity,
        "quantity": quantity,
        "profit_loss": profit_loss,
        "direction": "Long",
    }


def _make_trade(ticker, date_str, trade_type="buy", price=50.0, quantity=100):
    """Build a minimal raw-trade dict (from the trades table)."""
    return {
        "id": hash((ticker, date_str, trade_type)),
        "ticker": ticker,
        "date": date_str,
        "trade_type": trade_type,
        "price": price,
        "quantity": quantity,
        "platform_id": 1,
        "direction": "Long",
    }


def _make_opt(ticker, trade_date_str, close_date_str=None, profit_loss=0.0,
              status="closed", opt_id=1, strategy="cash secured put"):
    """Build a minimal option-trade dict."""
    return {
        "id": opt_id,
        "ticker": ticker,
        "trade_date": trade_date_str,
        "close_date": close_date_str,
        "profit_loss": profit_loss,
        "status": status,
        "strategy": strategy,
        "quantity": 1,
        "option_open_price": 2.0,
    }


# ---------------------------------------------------------------------------
# _parse_date tests
# ---------------------------------------------------------------------------

class TestParseDate:
    def test_string_iso(self):
        result = _parse_date("2024-03-15")
        assert result == datetime.datetime(2024, 3, 15)

    def test_date_object(self):
        d = datetime.date(2024, 6, 1)
        result = _parse_date(d)
        assert result == datetime.datetime(2024, 6, 1)

    def test_datetime_object(self):
        dt = datetime.datetime(2024, 6, 1, 12, 0)
        assert _parse_date(dt) == dt

    def test_none_returns_none(self):
        assert _parse_date(None) is None

    def test_invalid_string_returns_none(self):
        assert _parse_date("not-a-date") is None


# ---------------------------------------------------------------------------
# detect_wash_sales — stock loss scenarios
# ---------------------------------------------------------------------------

class TestWashSaleStockLoss:

    def test_no_replacement_buy_no_wash_sale(self):
        """A stock loss with no nearby buy is not a wash sale."""
        pos = _make_pos("AAPL", "2024-01-01", "2024-03-01", profit_loss=-500)
        # buy is well outside the 30-day window
        trade = _make_trade("AAPL", "2024-05-01", trade_type="buy")
        result = detect_wash_sales([pos], [], [trade], [])
        assert result == []

    def test_replacement_buy_after_sale_triggers_wash(self):
        """Buy within 30 days AFTER the loss sale → wash sale."""
        pos = _make_pos("AAPL", "2024-01-01", "2024-03-01", profit_loss=-500)
        trade = _make_trade("AAPL", "2024-03-15", trade_type="buy")  # 14 days after
        result = detect_wash_sales([pos], [], [trade], [])
        assert len(result) == 1
        ws = result[0]
        assert ws["ticker"] == "AAPL"
        assert ws["asset_type"] == "Stock"
        assert ws["disallowed_loss"] == pytest.approx(500.0)
        assert ws["replacement_type"] == "Stock Buy"

    def test_replacement_buy_before_sale_triggers_wash(self):
        """Buy within 30 days BEFORE the loss sale → wash sale."""
        pos = _make_pos("AAPL", "2024-01-01", "2024-03-20", profit_loss=-300)
        trade = _make_trade("AAPL", "2024-03-01", trade_type="buy")  # 19 days before
        result = detect_wash_sales([pos], [], [trade], [])
        assert len(result) == 1
        assert result[0]["disallowed_loss"] == pytest.approx(300.0)

    def test_replacement_buy_outside_window_no_wash(self):
        """Buy exactly 31 days after sale → NOT a wash sale."""
        pos = _make_pos("AAPL", "2024-01-01", "2024-03-01", profit_loss=-200)
        # 31 days after 2024-03-01 = 2024-04-01
        trade = _make_trade("AAPL", "2024-04-01", trade_type="buy")
        result = detect_wash_sales([pos], [], [trade], [])
        assert result == []

    def test_gain_not_flagged(self):
        """A profitable stock sale is never a wash sale regardless of repurchase."""
        pos = _make_pos("AAPL", "2024-01-01", "2024-03-01", profit_loss=+800)
        trade = _make_trade("AAPL", "2024-03-05", trade_type="buy")
        result = detect_wash_sales([pos], [], [trade], [])
        assert result == []

    def test_different_ticker_no_wash(self):
        """Buy of a different ticker does not trigger wash sale."""
        pos = _make_pos("AAPL", "2024-01-01", "2024-03-01", profit_loss=-400)
        trade = _make_trade("MSFT", "2024-03-05", trade_type="buy")
        result = detect_wash_sales([pos], [], [trade], [])
        assert result == []

    def test_sell_trade_not_replacement(self):
        """A sell trade of the same ticker does not count as a replacement."""
        pos = _make_pos("AAPL", "2024-01-01", "2024-03-01", profit_loss=-400)
        trade = _make_trade("AAPL", "2024-03-05", trade_type="sell")
        result = detect_wash_sales([pos], [], [trade], [])
        assert result == []

    def test_cross_platform_wash_sale(self):
        """Different platform_id on the replacement buy still triggers wash sale."""
        pos = _make_pos("TSLA", "2024-02-01", "2024-04-01", profit_loss=-1000)
        trade = _make_trade("TSLA", "2024-04-10", trade_type="buy")
        trade["platform_id"] = 2  # different platform
        result = detect_wash_sales([pos], [], [trade], [])
        assert len(result) == 1
        assert result[0]["disallowed_loss"] == pytest.approx(1000.0)

    def test_basis_adj_per_share_computed(self):
        """Basis adjustment per share = disallowed_loss / replacement_quantity."""
        pos = _make_pos("NVDA", "2024-01-01", "2024-02-01", profit_loss=-300, quantity=100)
        trade = _make_trade("NVDA", "2024-02-10", trade_type="buy", quantity=100)
        result = detect_wash_sales([pos], [], [trade], [])
        assert len(result) == 1
        assert result[0]["basis_adj_per_share"] == pytest.approx(3.0)  # 300 / 100

    def test_same_day_buy_excluded(self):
        """A buy on the exact same day as the loss sale is excluded (settlement)."""
        pos = _make_pos("AAPL", "2024-01-01", "2024-03-01", profit_loss=-500)
        trade = _make_trade("AAPL", "2024-03-01", trade_type="buy")  # same day
        result = detect_wash_sales([pos], [], [trade], [])
        assert result == []


# ---------------------------------------------------------------------------
# detect_wash_sales — stock loss + option replacement
# ---------------------------------------------------------------------------

class TestWashSaleOptionReplacement:

    def test_stock_loss_option_open_triggers_wash(self):
        """Selling stock at a loss and opening an option on same ticker → wash sale."""
        pos = _make_pos("AAPL", "2024-01-01", "2024-03-01", profit_loss=-600)
        opt = _make_opt("AAPL", trade_date_str="2024-03-10", status="open", opt_id=99)
        result = detect_wash_sales([pos], [], [], [opt])
        assert len(result) == 1
        ws = result[0]
        assert ws["ticker"] == "AAPL"
        assert "Option Open" in ws["replacement_type"]
        assert ws["disallowed_loss"] == pytest.approx(600.0)
        # No per-share adj for option replacements
        assert ws["basis_adj_per_share"] is None

    def test_stock_loss_option_outside_window_no_wash(self):
        """Option opened 31 days after loss sale → no wash sale."""
        pos = _make_pos("AAPL", "2024-01-01", "2024-03-01", profit_loss=-600)
        opt = _make_opt("AAPL", trade_date_str="2024-04-02", status="open", opt_id=88)
        result = detect_wash_sales([pos], [], [], [opt])
        assert result == []


# ---------------------------------------------------------------------------
# detect_wash_sales — option loss scenarios
# ---------------------------------------------------------------------------

class TestWashSaleOptionLoss:

    def test_option_loss_stock_buy_triggers_wash(self):
        """Option closed at a loss + stock buy within window → wash sale."""
        opt = _make_opt(
            "TSLA",
            trade_date_str="2024-01-15",
            close_date_str="2024-03-01",
            profit_loss=-250.0,
            status="closed",
            opt_id=1,
        )
        trade = _make_trade("TSLA", "2024-03-10", trade_type="buy")
        result = detect_wash_sales([], [opt], [trade], [opt])
        assert len(result) == 1
        ws = result[0]
        assert ws["asset_type"] == "Option"
        assert ws["disallowed_loss"] == pytest.approx(250.0)

    def test_option_loss_new_option_triggers_wash(self):
        """Option closed at loss + new option on same ticker within window → wash sale."""
        closed_opt = _make_opt(
            "MSFT",
            trade_date_str="2024-01-01",
            close_date_str="2024-03-01",
            profit_loss=-180.0,
            status="closed",
            opt_id=10,
        )
        new_opt = _make_opt(
            "MSFT",
            trade_date_str="2024-03-12",
            status="open",
            opt_id=11,
        )
        # all_option_trades includes both
        result = detect_wash_sales([], [closed_opt], [], [closed_opt, new_opt])
        assert len(result) == 1
        assert result[0]["disallowed_loss"] == pytest.approx(180.0)

    def test_option_self_excluded_as_replacement(self):
        """The same option trade is never treated as its own replacement."""
        opt = _make_opt(
            "MSFT",
            trade_date_str="2024-01-01",
            close_date_str="2024-03-01",
            profit_loss=-200.0,
            status="closed",
            opt_id=42,
        )
        # Only pass the same opt in all_option_trades — should not self-flag
        result = detect_wash_sales([], [opt], [], [opt])
        assert result == []

    def test_option_gain_not_flagged(self):
        """A profitable option close is never a wash sale."""
        opt = _make_opt(
            "AAPL",
            trade_date_str="2024-01-01",
            close_date_str="2024-03-01",
            profit_loss=+350.0,
            status="closed",
            opt_id=5,
        )
        trade = _make_trade("AAPL", "2024-03-05", trade_type="buy")
        result = detect_wash_sales([], [opt], [trade], [opt])
        assert result == []


# ---------------------------------------------------------------------------
# detect_wash_sales — year attribution
# ---------------------------------------------------------------------------

class TestWashSaleYearAttribution:

    def test_year_is_sale_year_for_stocks(self):
        pos = _make_pos("NVDA", "2023-11-01", "2023-12-28", profit_loss=-400)
        trade = _make_trade("NVDA", "2024-01-05", trade_type="buy")  # within 30 days, new year
        result = detect_wash_sales([pos], [], [trade], [])
        assert len(result) == 1
        assert result[0]["year"] == 2023  # year of the SALE, not the repurchase

    def test_year_is_close_year_for_options(self):
        opt = _make_opt(
            "AMD",
            trade_date_str="2023-11-15",
            close_date_str="2023-12-30",
            profit_loss=-150.0,
            status="closed",
            opt_id=7,
        )
        trade = _make_trade("AMD", "2024-01-10", trade_type="buy")
        result = detect_wash_sales([], [opt], [trade], [opt])
        assert len(result) == 1
        assert result[0]["year"] == 2023
