import streamlit as st
from sqlalchemy import text

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
def insert_position(ticker, trade_type, position_type, entry_price, quantity, entry_time, notes=None):
    conn = get_st_connection()
    with conn.session as session:
        session.execute(
            text("""
            INSERT INTO positions (ticker, trade_type, position_type, entry_price, quantity, entry_time, notes)
            VALUES (:ticker, :trade_type, :position_type, :entry_price, :quantity, :entry_time, :notes)
            """),
            {
                "ticker": ticker,
                "trade_type": trade_type,
                "position_type": position_type,
                "entry_price": entry_price,
                "quantity": quantity,
                "entry_time": entry_time,
                "notes": notes,
            }
        )
    st.cache_data.clear()

def update_position(position_id, **kwargs):
    conn = get_st_connection()
    columns = []
    values = []
    for key, value in kwargs.items():
        columns.append(f"{key} = %s")
        values.append(value)
    if not columns:
        return
    values.append(position_id)
    with conn.session as session:
        session.execute(
            f"UPDATE positions SET {', '.join(columns)} WHERE id = %s",
            values
        )
    st.cache_data.clear()

@st.cache_data(ttl=60, show_spinner=False)
def load_positions():
    conn = get_st_connection()
    # Comment out the rest to avoid crash
    return []

@st.cache_data(ttl=60, show_spinner=False)
def load_closed_positions():
    conn = get_st_connection()
    with conn.session as session:
        result = session.execute(text("SELECT id, ticker, trade_type, position_type, entry_price, quantity, exit_price, exit_time, entry_time, profit_loss, notes FROM positions WHERE position_type = 'CLOSE'"))
        rows = result.fetchall()
        columns = ["id", "ticker", "trade_type", "position_type", "entry_price", "quantity", "exit_price", "exit_time", "entry_time", "profit_loss", "notes"]
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

def close_option_trade(trade_id, status, close_date, option_close_price):
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
                profit_loss = option_open_price - option_close_price
            else:
                profit_loss = option_close_price - option_open_price
        else:
            profit_loss = None
        session.execute(
            text("UPDATE option_trades SET status = :status, close_date = :close_date, option_close_price = :option_close_price, profit_loss = :profit_loss WHERE id = :trade_id"),
            {
                "status": status,
                "close_date": close_date,
                "option_close_price": option_close_price,
                "profit_loss": profit_loss,
                "trade_id": trade_id,
            }
        )
    st.cache_data.clear()
