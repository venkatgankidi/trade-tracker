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

def insert_option_trade(ticker, platform_id, strategy, strike_price, expiry_date, trade_date, transaction_type, option_open_price, notes=None, open_fee=0):
    conn = get_st_connection()
    with conn.session as session:
        session.execute(
            text("""
            INSERT INTO option_trades (ticker, platform_id, strategy, strike_price, expiry_date, trade_date, transaction_type, option_open_price, notes, open_fee)
            VALUES (:ticker, :platform_id, :strategy, :strike_price, :expiry_date, :trade_date, :transaction_type, :option_open_price, :notes, :open_fee)
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
                "open_fee": open_fee,
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

def close_option_trade(trade_id, status, close_date, option_close_price, notes=None, close_fee=0):
    conn = get_st_connection()
    with conn.session as session:
        # Get transaction_type, option_open_price, open_fee for this trade
        result = session.execute(text("SELECT transaction_type, option_open_price, open_fee FROM option_trades WHERE id = :trade_id"), {"trade_id": trade_id})
        row = result.fetchone()
        if row:
            transaction_type, option_open_price, open_fee = row
            option_open_price = float(option_open_price) if option_open_price is not None else 0.0
            option_close_price = float(option_close_price) if option_close_price is not None else 0.0
            open_fee = float(open_fee) if open_fee is not None else 0.0
            close_fee = float(close_fee) if close_fee is not None else 0.0
            total_fee = open_fee + close_fee
            if transaction_type == "credit":
                profit_loss = (option_open_price - option_close_price) * 100 - total_fee
            else:
                profit_loss = (option_close_price - option_open_price) * 100 - total_fee
        else:
            profit_loss = None
        session.execute(
            text("UPDATE option_trades SET status = :status, close_date = :close_date, option_close_price = :option_close_price, close_fee = :close_fee, profit_loss = :profit_loss, notes = :notes WHERE id = :trade_id"),
            {
                "status": status,
                "close_date": close_date,
                "option_close_price": option_close_price,
                "close_fee": close_fee,
                "profit_loss": profit_loss,
                "notes": notes,
                "trade_id": trade_id,
            }
        )
        session.commit()
    st.cache_data.clear()

def sync_positions_from_trades():
    """
    Syncs the positions table with the trades table. Handles partial sells by matching sells to open buy lots (FIFO).
    For each ticker/platform, creates closed positions for sold shares and open positions for remaining shares.
    """
    conn = get_st_connection()
    with conn.session as session:
        # Get all trades ordered by ticker, platform, date
        result = session.execute(text('''
            SELECT ticker, platform_id, price, quantity, date, trade_type
            FROM trades
            ORDER BY ticker, platform_id, date, id
        '''))
        trades = result.fetchall()
        # Group trades by (ticker, platform_id)
        from collections import defaultdict, deque
        trades_by_key = defaultdict(list)
        for row in trades:
            ticker, platform_id, price, quantity, date, trade_type = row
            trades_by_key[(ticker, platform_id)].append({
                'price': float(price),
                'quantity': float(quantity),
                'date': date,
                'trade_type': trade_type
            })
        # Remove all positions before upsert
        session.execute(text("DELETE FROM positions"))
        for (ticker, platform_id), trade_list in trades_by_key.items():
            open_lots = deque()
            closed_positions = []
            for trade in trade_list:
                if trade['trade_type'].lower() == 'buy':
                    open_lots.append({
                        'price': trade['price'],
                        'quantity': trade['quantity'],
                        'entry_date': trade['date'],
                        'remaining': trade['quantity']
                    })
                elif trade['trade_type'].lower() == 'sell':
                    sell_qty = trade['quantity']
                    sell_price = trade['price']
                    sell_date = trade['date']
                    # FIFO match sell to open lots
                    while sell_qty > 0 and open_lots:
                        lot = open_lots[0]
                        lot_qty = lot['remaining']
                        matched_qty = min(lot_qty, sell_qty)
                        profit_loss = (sell_price - lot['price']) * matched_qty
                        # Insert closed position for matched_qty
                        session.execute(text('''
                            INSERT INTO positions (ticker, trade_type, position_status, entry_price, quantity, entry_date, exit_price, exit_date, platform_id, profit_loss)
                            VALUES (:ticker, :trade_type, 'close', :entry_price, :quantity, :entry_date, :exit_price, :exit_date, :platform_id, :profit_loss)
                        '''), {
                            'ticker': ticker,
                            'trade_type': None,
                            'entry_price': lot['price'],
                            'quantity': matched_qty,
                            'entry_date': lot['entry_date'],
                            'exit_price': sell_price,
                            'exit_date': sell_date,
                            'platform_id': platform_id,
                            'profit_loss': profit_loss
                        })
                        lot['remaining'] -= matched_qty
                        sell_qty -= matched_qty
                        if lot['remaining'] == 0:
                            open_lots.popleft()
                        # If sell_qty == 0, done
            # After all trades, any open_lots are open positions
            for lot in open_lots:
                session.execute(text('''
                    INSERT INTO positions (ticker, trade_type, position_status, entry_price, quantity, entry_date, platform_id, profit_loss)
                    VALUES (:ticker, NULL, 'open', :entry_price, :quantity, :entry_date, :platform_id, NULL)
                '''), {
                    'ticker': ticker,
                    'entry_price': lot['price'],
                    'quantity': lot['remaining'],
                    'entry_date': lot['entry_date'],
                    'platform_id': platform_id
                })
        session.commit()
    st.cache_data.clear()
