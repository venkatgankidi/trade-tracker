import streamlit as st
from sqlalchemy import text
import datetime
import logging
from typing import Any, Dict, Optional, List

# Set up logging
logger = logging.getLogger(__name__)

# --- PlatformCache and related functions ---
class PlatformCache:
    def __init__(self):
        self.cache: Dict[str, int] = {}

    def keys(self):
        return list(self.cache.keys())

    def get(self, key: str) -> Optional[int]:
        return self.cache.get(key)

PLATFORM_CACHE = PlatformCache()

def get_st_connection():
    """Get a Streamlit SQL connection object."""
    return st.connection("postgresql", type="sql")

def load_platforms() -> None:
    """Load platforms from the database into the cache."""
    if not PLATFORM_CACHE.cache:
        try:
            conn = get_st_connection()
            with conn.session as session:
                result = session.execute(text("SELECT id, name FROM platforms ORDER BY name DESC"))
                PLATFORM_CACHE.cache = {row[1]: row[0] for row in result.fetchall()}
        except Exception as e:
            logger.error(f"Error connecting to the database: {e}")

# --- Utility function for platform mapping ---
def map_platform_id_to_name(platform_id: int, platform_cache: PlatformCache = PLATFORM_CACHE) -> Optional[str]:
    """Map a platform_id to its name using the platform cache."""
    id_to_name = {v: k for k, v in platform_cache.cache.items()}
    return id_to_name.get(platform_id)

# --- Existing db_utils.py functions for positions management ---
def insert_position(
    ticker: str,
    trade_type: str,
    position_status: str,
    entry_price: float,
    quantity: float,
    entry_date: Any,
    platform_id: Optional[int] = None
) -> None:
    """Insert a new position into the database."""
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

def update_position(position_id: int, **kwargs) -> None:
    """Update a position in the database."""
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
def load_positions() -> List[Dict[str, Any]]:
    """Load open positions from the database."""
    conn = get_st_connection()
    with conn.session as session:
        result = session.execute(
            text("SELECT id, ticker, trade_type, position_status, entry_price, quantity, entry_date, platform_id FROM positions WHERE position_status != 'close'")
        )
        rows = result.fetchall()
        columns = ["id", "ticker", "trade_type", "position_status", "entry_price", "quantity", "entry_date", "platform_id"]
        return [dict(zip(columns, row)) for row in rows]

@st.cache_data(ttl=60, show_spinner=False)
def load_closed_positions() -> List[Dict[str, Any]]:
    """Load closed positions from the database."""
    conn = get_st_connection()
    with conn.session as session:
        result = session.execute(text("SELECT id, ticker, trade_type, position_status, entry_price, quantity, exit_price, exit_date, entry_date, profit_loss, platform_id FROM positions WHERE position_status = 'close'"))
        rows = result.fetchall()
        columns = ["id", "ticker", "trade_type", "position_status", "entry_price", "quantity", "exit_price", "exit_date", "entry_date", "profit_loss", "platform_id"]
        return [dict(zip(columns, row)) for row in rows]

def insert_option_trade(
    ticker: str,
    platform_id: int,
    strategy: str,
    strike_price: float,
    expiry_date: Any,
    trade_date: Any,
    transaction_type: str,
    option_open_price: float,
    notes: Optional[str] = None,
    open_fee: float = 0
) -> None:
    """Insert a new option trade into the database."""
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

def update_option_trade(trade_id: int, **kwargs) -> None:
    """Update an option trade in the database."""
    conn = get_st_connection()
    columns = []
    params = {}
    for key, value in kwargs.items():
        columns.append(f"{key} = :{key}")
        params[key] = value
    if not columns:
        return
    params["trade_id"] = trade_id
    with conn.session as session:
        session.execute(
            text(f"UPDATE option_trades SET {', '.join(columns)} WHERE id = :trade_id"),
            params
        )
        session.commit()
    st.cache_data.clear()

@st.cache_data(ttl=60, show_spinner=False)
def load_option_trades(status=None) -> List[Dict[str, Any]]:
    """Load option trades from the database."""
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
    Optimized: Syncs the positions table with the trades table using batch inserts and minimal deletions.
    Handles partial sells by matching sells to open buy lots (FIFO).
    Only deletes positions for tickers/platforms being updated.
    Rounds quantities to 6 decimal places to avoid floating point precision issues.
    """
    conn = get_st_connection()
    with conn.session as session:
        # Get all trades ordered by ticker, platform, date
        # Select id as well and order by date first, then id as a tiebreaker to
        # correctly handle multiple trades on the same date (day trades). This
        # ensures chronological ordering where date is primary and id preserves
        # insertion order for same-day events.
        result = session.execute(text('''
            SELECT id, ticker, platform_id, price, quantity, date, trade_type
            FROM trades
            ORDER BY ticker, platform_id, date, id
        '''))
        trades = result.fetchall()
        from collections import defaultdict, deque
        trades_by_key = defaultdict(list)
        for row in trades:
            # row layout: id, ticker, platform_id, price, quantity, date, trade_type
            _id, ticker, platform_id, price, quantity, date, trade_type = row
            # Normalize values: ensure numeric types, normalized trade_type and skip zero qty
            try:
                qty = round(float(quantity), 6)
            except Exception:
                qty = 0.0
            if qty == 0:
                # skip no-op trades
                continue
            ttype = (str(trade_type) if trade_type is not None else "").strip().lower()
            trades_by_key[(ticker, platform_id)].append({
                'id': _id,
                'price': float(price) if price is not None else 0.0,
                'quantity': qty,
                'date': date,
                'trade_type': ttype
            })
        # Prepare batch inserts and minimal deletions
        all_keys = list(trades_by_key.keys())
        # Delete only positions for tickers/platforms being updated
        for ticker, platform_id in all_keys:
            session.execute(text("DELETE FROM positions WHERE ticker = :ticker AND platform_id = :platform_id"), {"ticker": ticker, "platform_id": platform_id})
        closed_positions = []
        open_positions = []
        for (ticker, platform_id), trade_list in trades_by_key.items():
            open_lots = deque()
            for trade in trade_list:
                if trade['trade_type'].lower() == 'buy':
                    open_lots.append({
                        'price': trade['price'],
                        'quantity': trade['quantity'],
                        'entry_date': trade['date'],
                        'remaining': round(trade['quantity'], 6)  # Round to 6 decimal places
                    })
                elif trade['trade_type'].lower() == 'sell':
                    sell_qty = round(trade['quantity'], 6)  # Round to 6 decimal places
                    sell_price = trade['price']
                    sell_date = trade['date']
                    while round(sell_qty, 6) > 0 and open_lots:  # Round comparison to 6 decimal places
                        lot = open_lots[0]
                        lot_qty = round(lot['remaining'], 6)  # Round to 6 decimal places
                        matched_qty = round(min(lot_qty, sell_qty), 6)  # Round to 6 decimal places
                        profit_loss = round((sell_price - lot['price']) * matched_qty, 2)  # Round profit/loss to 2 decimal places
                        closed_positions.append({
                            'ticker': ticker,
                            'trade_type': None,
                            'position_status': 'close',
                            'entry_price': lot['price'],
                            'quantity': matched_qty,
                            'entry_date': lot['entry_date'],
                            'exit_price': sell_price,
                            'exit_date': sell_date,
                            'platform_id': platform_id,
                            'profit_loss': profit_loss
                        })
                        lot['remaining'] = round(lot['remaining'] - matched_qty, 6)  # Round to 6 decimal places
                        sell_qty = round(sell_qty - matched_qty, 6)  # Round to 6 decimal places
                        if abs(lot['remaining']) < 1e-6:  # Compare with small epsilon instead of exact 0
                            open_lots.popleft()
            # After all trades, any open_lots are open positions
            for lot in open_lots:
                open_positions.append({
                    'ticker': ticker,
                    'trade_type': None,
                    'position_status': 'open',
                    'entry_price': lot['price'],
                    'quantity': lot['remaining'],
                    'entry_date': lot['entry_date'],
                    'platform_id': platform_id,
                    'profit_loss': None
                })
        # Batch insert closed positions
        if closed_positions:
            session.execute(text('''
                INSERT INTO positions (ticker, trade_type, position_status, entry_price, quantity, entry_date, exit_price, exit_date, platform_id, profit_loss)
                VALUES 
                ''' + ',\n'.join([
                    f"(:ticker{i}, :trade_type{i}, :position_status{i}, :entry_price{i}, :quantity{i}, :entry_date{i}, :exit_price{i}, :exit_date{i}, :platform_id{i}, :profit_loss{i})"
                    for i in range(len(closed_positions))
                ])), {
                    **{f"ticker{i}": p['ticker'] for i, p in enumerate(closed_positions)},
                    **{f"trade_type{i}": p['trade_type'] for i, p in enumerate(closed_positions)},
                    **{f"position_status{i}": p['position_status'] for i, p in enumerate(closed_positions)},
                    **{f"entry_price{i}": p['entry_price'] for i, p in enumerate(closed_positions)},
                    **{f"quantity{i}": p['quantity'] for i, p in enumerate(closed_positions)},
                    **{f"entry_date{i}": p['entry_date'] for i, p in enumerate(closed_positions)},
                    **{f"exit_price{i}": p['exit_price'] for i, p in enumerate(closed_positions)},
                    **{f"exit_date{i}": p['exit_date'] for i, p in enumerate(closed_positions)},
                    **{f"platform_id{i}": p['platform_id'] for i, p in enumerate(closed_positions)},
                    **{f"profit_loss{i}": p['profit_loss'] for i, p in enumerate(closed_positions)},
                }
            )
        # Batch insert open positions
        if open_positions:
            session.execute(text('''
                INSERT INTO positions (ticker, trade_type, position_status, entry_price, quantity, entry_date, platform_id, profit_loss)
                VALUES 
                ''' + ',\n'.join([
                    f"(:ticker{i}, :trade_type{i}, :position_status{i}, :entry_price{i}, :quantity{i}, :entry_date{i}, :platform_id{i}, :profit_loss{i})"
                    for i in range(len(open_positions))
                ])), {
                    **{f"ticker{i}": p['ticker'] for i, p in enumerate(open_positions)},
                    **{f"trade_type{i}": p['trade_type'] for i, p in enumerate(open_positions)},
                    **{f"position_status{i}": p['position_status'] for i, p in enumerate(open_positions)},
                    **{f"entry_price{i}": p['entry_price'] for i, p in enumerate(open_positions)},
                    **{f"quantity{i}": p['quantity'] for i, p in enumerate(open_positions)},
                    **{f"entry_date{i}": p['entry_date'] for i, p in enumerate(open_positions)},
                    **{f"platform_id{i}": p['platform_id'] for i, p in enumerate(open_positions)},
                    **{f"profit_loss{i}": p['profit_loss'] for i, p in enumerate(open_positions)},
                }
            )
        session.commit()
    st.cache_data.clear()

def insert_trade(
    ticker: str,
    platform_id: int,
    price: float,
    quantity: float,
    date: any,
    trade_type: str
) -> None:
    """Insert a new trade into the trades table."""
    conn = get_st_connection()
    with conn.session as session:
        session.execute(
            text("""
            INSERT INTO trades (ticker, platform_id, price, quantity, date, trade_type)
            VALUES (:ticker, :platform_id, :price, :quantity, :date, :trade_type)
            """),
            {
                "ticker": ticker,
                "platform_id": platform_id,
                "price": price,
                "quantity": quantity,
                "date": date,
                "trade_type": trade_type,
            }
        )
        session.commit()
    st.cache_data.clear()


# --- Last upload metadata helpers (DB-backed) -----------------------------
def set_last_upload_time(ts: Optional[str] = None) -> None:
    """Persist the last upload timestamp (UTC ISO string) into the DB.

    If ts is None the current UTC time is used. This function assumes the
    `app_metadata` table is present (managed via migrations/schema.sql). If the
    table is missing this will raise an error from the DB which is intentional
    for environments that require explicit migrations.
    """
    if ts is None:
        ts = datetime.datetime.utcnow().isoformat()
    try:
        conn = get_st_connection()
        with conn.session as session:
            # upsert the key/value. Requires `app_metadata` to exist.
            session.execute(
                text("""
                INSERT INTO app_metadata (key, value) VALUES (:key, :value)
                ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value
                """),
                {"key": "last_csv_upload", "value": ts}
            )
            session.commit()
    except Exception as e:
        logger.error(f"Failed to write last upload metadata to DB: {e}")

def get_last_upload_time() -> Optional[str]:
    """Return the last upload UTC ISO timestamp as a string from the DB, or None if not set.

    This function assumes the `app_metadata` table exists.
    """
    try:
        conn = get_st_connection()
        with conn.session as session:
            result = session.execute(text("SELECT value FROM app_metadata WHERE key = :key"), {"key": "last_csv_upload"})
            row = result.fetchone()
            return row[0] if row else None
    except Exception as e:
        logger.error(f"Failed to read last upload metadata from DB: {e}")
        return None
