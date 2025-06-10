import streamlit as st
from sqlalchemy import text
import datetime

# --- PlatformCache and related functions (merged from db.py) ---
class PlatformCache:
    def __init__(self):
        self.cache = {}

    def keys(self):
        return self.cache.keys()

    def get(self, key):
        return self.cache.get(key)

PLATFORM_CACHE = PlatformCache()

def get_st_connection():
    return st.connection("postgresql", type="sql")

def load_platforms():
    if not PLATFORM_CACHE.cache:
        try:
            conn = get_st_connection()
            with conn.session as session:
                result = session.execute(text("SELECT id, name FROM platforms ORDER BY name DESC"))
                PLATFORM_CACHE.cache = {row[1]: row[0] for row in result.fetchall()}
        except Exception as e:
            print("Error connecting to the database:", e)

# --- Existing db_utils.py functions for positions management ---
def insert_position(ticker, trade_type, position_status, entry_price, quantity, entry_date, platform_id=None):
    conn = get_st_connection()
    with conn.session as session:
        session.execute(
            text("""
            INSERT INTO positions (ticker, trade_type, position_status, entry_price, quantity, entry_date, platform_id)
            VALUES (:ticker, :trade_type, :position_status, :entry_price, :quantity, :entry_date, :platform_id)
            """),
            {
                "ticker": ticker,
                "trade_type": trade_type,
                "position_status": position_status,
                "entry_price": entry_price,
                "quantity": quantity,
                "entry_date": entry_date,
                "platform_id": platform_id,
            }
        )
        session.commit()
    st.cache_data.clear()

def update_position(position_id, **kwargs):
    conn = get_st_connection()
    columns = []
    params = {}
    for key, value in kwargs.items():
        columns.append(f"{key} = :{key}")
        params[key] = value
    if not columns:
        return
    params["position_id"] = position_id
    with conn.session as session:
        session.execute(
            text(f"UPDATE positions SET {', '.join(columns)} WHERE id = :position_id"),
            params
        )
        session.commit()
    st.cache_data.clear()

@st.cache_data(ttl=60, show_spinner=False)
def load_positions():
    conn = get_st_connection()
    with conn.session as session:
        result = session.execute(
            text("SELECT id, ticker, trade_type, position_status, entry_price, quantity, entry_date, platform_id FROM positions WHERE position_status != 'close'")
        )
        rows = result.fetchall()
        columns = ["id", "ticker", "trade_type", "position_status", "entry_price", "quantity", "entry_date", "platform_id"]
        return [dict(zip(columns, row)) for row in rows]

@st.cache_data(ttl=60, show_spinner=False)
def load_closed_positions():
    conn = get_st_connection()
    with conn.session as session:
        result = session.execute(text("SELECT id, ticker, trade_type, position_status, entry_price, quantity, exit_price, exit_date, entry_date, profit_loss, platform_id FROM positions WHERE position_status = 'close'"))
        rows = result.fetchall()
        columns = ["id", "ticker", "trade_type", "position_status", "entry_price", "quantity", "exit_price", "exit_date", "entry_date", "profit_loss", "platform_id"]
        return [dict(zip(columns, row)) for row in rows]

def insert_option_trade(ticker, platform_id, strategy, strike_price, expiry_date, trade_date, transaction_type, option_open_price, notes=None):
    conn = get_st_connection()
    with conn.session as session:
        session.execute(
            text("""
            INSERT INTO option_trades (ticker, platform_id, strategy, strike_price, expiry_date, trade_date, transaction_type, option_open_price, notes)
            VALUES (:ticker, :platform_id, :strategy, :strike_price, :expiry_date, :trade_date, :transaction_type, :option_open_price, :notes)
            """),
            {
                "ticker": ticker,
                "platform_id": platform_id,
                "strategy": strategy,
                "strike_price": strike_price,
                "expiry_date": expiry_date,
                "trade_date": trade_date,
                "transaction_type": transaction_type,
                "option_open_price": option_open_price,
                "notes": notes,
            }
        )
        session.commit()
    st.cache_data.clear()

def update_option_trade(trade_id, **kwargs):
    conn = get_st_connection()
    columns = []
    values = []
    for key, value in kwargs.items():
        columns.append(f"{key} = %s")
        values.append(value)
    if not columns:
        return
    values.append(trade_id)
    with conn.session as session:
        session.execute(
            text(f"UPDATE option_trades SET {', '.join(columns)} WHERE id = :trade_id"),
            {**dict(zip([col.split(' = ')[0] for col in columns], values[:-1])), "trade_id": values[-1]}
        )
        session.commit()
    st.cache_data.clear()

@st.cache_data(ttl=60, show_spinner=False)
def load_option_trades(status=None):
    conn = get_st_connection()
    with conn.session as session:
        if status:
            result = session.execute(text("SELECT * FROM option_trades WHERE status = :status"), {"status": status})
        else:
            result = session.execute(text("SELECT * FROM option_trades"))
        rows = result.fetchall()
        columns = result.keys()
        return [dict(zip(columns, row)) for row in rows]

def close_option_trade(trade_id, status, close_date, option_close_price, notes=None):
    conn = get_st_connection()
    with conn.session as session:
        # Get transaction_type and option_open_price for this trade
        result = session.execute(text("SELECT transaction_type, option_open_price FROM option_trades WHERE id = :trade_id"), {"trade_id": trade_id})
        row = result.fetchone()
        if row:
            transaction_type, option_open_price = row
            option_open_price = float(option_open_price) if option_open_price is not None else 0.0
            option_close_price = float(option_close_price) if option_close_price is not None else 0.0
            if transaction_type == "credit":
                profit_loss = (option_open_price - option_close_price) * 100
            else:
                profit_loss = (option_close_price - option_open_price) * 100
        else:
            profit_loss = None
        session.execute(
            text("UPDATE option_trades SET status = :status, close_date = :close_date, option_close_price = :option_close_price, profit_loss = :profit_loss, notes = :notes WHERE id = :trade_id"),
            {
                "status": status,
                "close_date": close_date,
                "option_close_price": option_close_price,
                "profit_loss": profit_loss,
                "notes": notes,
                "trade_id": trade_id,
            }
        )
        session.commit()
    st.cache_data.clear()

def sync_positions_from_trades():
    """
    Syncs the positions table with the trades table. For each ticker/platform, creates or updates a position reflecting all trades (open or closed).
    If net quantity > 0, upserts as open. If net quantity == 0, upserts as close.
    The quantity in the position is always the total buy quantity.
    Calculates profit_loss for closed positions.
    Trade type: day (same day), swing (<=30 days), position (>30 days).
    Prevents duplicate positions for the same ticker/platform.
    """
    conn = get_st_connection()
    with conn.session as session:
        # Aggregate trades by ticker and platform
        result = session.execute(text('''
            SELECT ticker, platform_id,
                SUM(CASE WHEN trade_type = 'Buy' THEN quantity ELSE 0 END) AS total_buy_qty,
                SUM(CASE WHEN trade_type = 'Sell' THEN quantity ELSE 0 END) AS total_sell_qty,
                SUM(CASE WHEN trade_type = 'Buy' THEN price * quantity ELSE 0 END) / NULLIF(SUM(CASE WHEN trade_type = 'Buy' THEN quantity ELSE 0 END), 0) AS avg_buy_price,
                MAX(CASE WHEN trade_type = 'Buy' THEN date ELSE NULL END) AS entry_date,
                SUM(CASE WHEN trade_type = 'Sell' THEN price * quantity ELSE 0 END) / NULLIF(SUM(CASE WHEN trade_type = 'Sell' THEN quantity ELSE 0 END), 0) AS avg_sell_price,
                MAX(CASE WHEN trade_type = 'Sell' THEN date ELSE NULL END) AS exit_date,
                MIN(CASE WHEN trade_type = 'Buy' THEN date ELSE NULL END) AS first_entry_date
            FROM trades
            GROUP BY ticker, platform_id
        '''))
        trades_summary = result.fetchall()
        for row in trades_summary:
            ticker, platform_id, total_buy_qty, total_sell_qty, avg_buy_price, entry_date, avg_sell_price, exit_date, first_entry_date = row
            net_quantity = (total_buy_qty or 0) - (total_sell_qty or 0)
            # Calculate profit/loss for closed positions
            profit_loss = None
            trade_type = None
            if entry_date and exit_date:
                try:
                    entry_dt = first_entry_date if isinstance(first_entry_date, (datetime.datetime, datetime.date)) else datetime.datetime.fromisoformat(str(first_entry_date))
                    exit_dt = exit_date if isinstance(exit_date, (datetime.datetime, datetime.date)) else datetime.datetime.fromisoformat(str(exit_date))
                    days_held = (exit_dt - entry_dt).days
                    if entry_dt == exit_dt:
                        trade_type = "day"
                    elif days_held <= 30:
                        trade_type = "swing"
                    else:
                        trade_type = "position"
                except Exception:
                    trade_type = None
            if net_quantity == 0 and total_buy_qty and total_sell_qty:
                profit_loss = (avg_sell_price - avg_buy_price) * total_sell_qty
            # Remove all existing positions for this ticker/platform before upsert
            session.execute(text("DELETE FROM positions WHERE ticker = :ticker AND platform_id = :platform_id"), {"ticker": ticker, "platform_id": platform_id})
            if net_quantity > 0:
                # Open position
                session.execute(text("""
                    INSERT INTO positions (ticker, trade_type, position_status, entry_price, quantity, entry_date, platform_id, profit_loss)
                    VALUES (:ticker, NULL, 'open', :entry_price, :quantity, :entry_date, :platform_id, NULL)
                """), {"ticker": ticker, "entry_price": avg_buy_price, "quantity": total_buy_qty, "entry_date": entry_date, "platform_id": platform_id})
            else:
                # Closed position
                session.execute(text("""
                    INSERT INTO positions (ticker, trade_type, position_status, entry_price, quantity, entry_date, exit_price, exit_date, platform_id, profit_loss)
                    VALUES (:ticker, :trade_type, 'close', :entry_price, :quantity, :entry_date, :exit_price, :exit_date, :platform_id, :profit_loss)
                """), {"ticker": ticker, "trade_type":trade_type, "entry_price": avg_buy_price, "quantity": total_buy_qty, "entry_date": entry_date, "exit_price": avg_sell_price, "exit_date": exit_date, "platform_id": platform_id, "profit_loss": profit_loss})
        session.commit()
    st.cache_data.clear()
