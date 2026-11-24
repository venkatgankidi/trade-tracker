import streamlit as st
from sqlalchemy import text
from sqlalchemy.pool import NullPool
import datetime
import logging
from collections import defaultdict, deque
from typing import Any, Callable, Dict, Iterable, List, Optional, Tuple
from config import Config
from ui.error_handling import handle_database_error

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

    # Convenience methods to make the cache behave more like a dict
    def __contains__(self, key: str) -> bool:
        return key in self.cache

    def __getitem__(self, key: str) -> int:
        return self.cache[key]

    def items(self):
        return self.cache.items()

    def values(self):
        return self.cache.values()

    def id_to_name_map(self) -> Dict[int, str]:
        """Return mapping of platform_id -> platform_name."""
        return {v: k for k, v in self.cache.items()}


PLATFORM_CACHE = PlatformCache()

# --- Granular cache registry ------------------------------------------------
# Maps domain group -> list of @st.cache_data-decorated functions.
_CACHE_REGISTRY: Dict[str, List[Callable[..., Any]]] = defaultdict(list)

# Downstream cache groups invalidated when a given domain changes.
_CACHE_DEPENDENCIES: Dict[str, Tuple[str, ...]] = {
    "positions": ("positions", "portfolio", "dashboard", "taxes", "reports"),
    "trades": ("trades", "taxes"),
    "options": ("options", "dashboard", "taxes", "reports"),
    "cash": ("cash", "dashboard"),
    "platforms": ("platforms", "cash", "dashboard", "portfolio"),
    "metadata": ("metadata",),
    "portfolio": ("portfolio", "dashboard"),
    "dashboard": ("dashboard",),
    "taxes": ("taxes",),
    "reports": ("reports",),
}


def register_cache(group: str, func: Callable[..., Any]) -> Callable[..., Any]:
    """Register a @st.cache_data function under a logical group for selective invalidation."""
    if func not in _CACHE_REGISTRY[group]:
        _CACHE_REGISTRY[group].append(func)
    return func


def clear_cache_selective(cache_types: Optional[List[str]] = None) -> None:
    """Clear only the cache groups affected by a write instead of wiping all caches.

    Avoids forcing unnecessary PostgreSQL queries and external API refetches when
    only a single table changed.

    Args:
        cache_types: List of cache types to clear. Options:
            - 'positions': Position, portfolio, dashboard, tax, and report caches
            - 'trades': Raw trade history and tax caches
            - 'options': Option trade, leg, dashboard, tax, and report caches
            - 'cash': Cash flow, platform cash, and dashboard caches
            - 'platforms': Platform and dependent caches
            - 'metadata': App metadata (e.g., last upload time)
            - 'all': Clear all st.cache_data caches
    """
    if cache_types is None:
        cache_types = ["all"]

    if "all" in cache_types:
        st.cache_data.clear()
        return

    groups_to_clear = set()
    for cache_type in cache_types:
        groups_to_clear.update(_CACHE_DEPENDENCIES.get(cache_type, (cache_type,)))

    cleared_any = False
    for group in groups_to_clear:
        for func in _CACHE_REGISTRY.get(group, []):
            clear_fn = getattr(func, "clear", None)
            if callable(clear_fn):
                clear_fn()
                cleared_any = True

    if not cleared_any:
        st.cache_data.clear()


def get_st_connection():
    """Get the shared Streamlit SQL connection (backed by NullPool)."""
    # Import here to avoid circular imports
    import app
    conn = getattr(app, "CONNECTION_POOL", None)
    if conn is not None:
        return conn
    return st.connection(
        "postgresql",
        type="sql",
        poolclass=NullPool,
        connect_args=Config.DB_CONNECT_ARGS,
    )


def _execute_in_chunks(
    session: Any,
    stmt: Any,
    rows: List[Dict[str, Any]],
    chunk_size: int = Config.DB_BATCH_SIZE,
) -> None:
    """Execute a parameterized DML statement in fixed-size executemany chunks.

    Bounding chunk size prevents PostgreSQL parser/bind memory spikes on low-RAM
    instances (e.g., Aiven Free Tier).
    """
    if not rows:
        return
    size = max(1, int(chunk_size))
    for start in range(0, len(rows), size):
        session.execute(stmt, rows[start : start + size])


@st.cache_data(ttl=Config.CACHE_TTL["platforms"], show_spinner=False)
def load_platforms_from_db() -> Dict[str, int]:
    """Load platforms from the database."""
    conn = get_st_connection()
    with conn.session as session:
        # Order by name ascending for predictable UI ordering
        result = session.execute(text("SELECT id, name FROM platforms ORDER BY name ASC"))
        return {row[1]: row[0] for row in result.fetchall()}


register_cache("platforms", load_platforms_from_db)


def load_platforms() -> None:
    """Load platforms from the database into the in-memory cache."""
    if not PLATFORM_CACHE.cache:
        try:
            PLATFORM_CACHE.cache = load_platforms_from_db()
        except Exception as e:
            logger.error(f"Error connecting to the database: {e}")
            PLATFORM_CACHE.cache = {}


# --- Utility function for platform mapping ---
def map_platform_id_to_name(platform_id: int, platform_cache: PlatformCache = PLATFORM_CACHE) -> Optional[str]:
    """Map a platform_id to its name using the platform cache."""
    id_to_name = {v: k for k, v in platform_cache.cache.items()}
    return id_to_name.get(platform_id)


# --- Positions management ---
@handle_database_error
def insert_position(
    ticker: str,
    trade_type: str,
    position_status: str,
    entry_price: float,
    quantity: float,
    entry_date: Any,
    platform_id: Optional[int] = None,
    direction: str = "Long",
) -> None:
    """Insert a new position into the database."""
    conn = get_st_connection()
    with conn.session as session:
        session.execute(
            text("""
            INSERT INTO positions (ticker, trade_type, position_status, entry_price, quantity, entry_date, platform_id, direction)
            VALUES (:ticker, :trade_type, :position_status, :entry_price, :quantity, :entry_date, :platform_id, :direction)
            """),
            {
                "ticker": ticker,
                "trade_type": trade_type,
                "position_status": position_status,
                "entry_price": entry_price,
                "quantity": quantity,
                "entry_date": entry_date,
                "platform_id": platform_id,
                "direction": direction,
            },
        )
        session.commit()
    clear_cache_selective(["positions"])


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
            params,
        )
        session.commit()
    clear_cache_selective(["positions"])


@st.cache_data(ttl=Config.CACHE_TTL["positions"], show_spinner=False)
def load_all_positions() -> Dict[str, List[Dict[str, Any]]]:
    """Load all positions from the database in a single query and split by status."""
    conn = get_st_connection()
    with conn.session as session:
        result = session.execute(text("""
            SELECT id, ticker, trade_type, position_status, entry_price,
                   quantity, entry_date, platform_id, exit_price, exit_date, profit_loss, direction
            FROM positions
            ORDER BY entry_date DESC
        """))
        rows = result.fetchall()
        columns = [
            "id", "ticker", "trade_type", "position_status", "entry_price",
            "quantity", "entry_date", "platform_id", "exit_price", "exit_date", "profit_loss", "direction",
        ]

        all_positions = [dict(zip(columns, row)) for row in rows]

        # Split by status
        open_positions = [p for p in all_positions if p.get("position_status") != "close"]
        closed_positions = [p for p in all_positions if p.get("position_status") == "close"]

        return {
            "open": open_positions,
            "closed": closed_positions,
            "all": all_positions,
        }


register_cache("positions", load_all_positions)


def load_positions() -> List[Dict[str, Any]]:
    """Load open positions from the cached positions payload."""
    return load_all_positions()["open"]


def load_closed_positions() -> List[Dict[str, Any]]:
    """Load closed positions from the cached positions payload."""
    return load_all_positions()["closed"]


# --- Option trades management ---
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
    open_fee: float = 0,
    quantity: int = 1,
) -> None:
    """Insert a new option trade into the database."""
    conn = get_st_connection()
    with conn.session as session:
        session.execute(
            text("""
            INSERT INTO option_trades (ticker, platform_id, strategy, strike_price, expiry_date, trade_date, transaction_type, option_open_price, notes, open_fee, quantity)
            VALUES (:ticker, :platform_id, :strategy, :strike_price, :expiry_date, :trade_date, :transaction_type, :option_open_price, :notes, :open_fee, :quantity)
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
                "quantity": quantity,
            },
        )
        session.commit()
    clear_cache_selective(["options"])


def insert_option_trade_with_legs(
    ticker: str,
    platform_id: int,
    strategy: str,
    strike_price: float,
    expiry_date: Any,
    trade_date: Any,
    transaction_type: str,
    option_open_price: float,
    legs: List[Dict[str, Any]],
    notes: Optional[str] = None,
    open_fee: float = 0,
    quantity: int = 1,
) -> None:
    """Insert a multi-leg option trade with its legs in a single transaction."""
    conn = get_st_connection()
    with conn.session as session:
        result = session.execute(
            text("""
            INSERT INTO option_trades (ticker, platform_id, strategy, strike_price, expiry_date, trade_date, transaction_type, option_open_price, notes, open_fee, quantity)
            VALUES (:ticker, :platform_id, :strategy, :strike_price, :expiry_date, :trade_date, :transaction_type, :option_open_price, :notes, :open_fee, :quantity)
            RETURNING id
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
                "quantity": quantity,
            },
        )
        trade_id = result.fetchone()[0]
        if legs:
            leg_rows = [
                {
                    "option_trade_id": trade_id,
                    "leg_type": leg["leg_type"],
                    "side": leg["side"],
                    "strike_price": leg["strike_price"],
                    "expiry_date": leg["expiry_date"],
                    "premium": leg["premium"],
                }
                for leg in legs
            ]
            _execute_in_chunks(
                session,
                text("""
                INSERT INTO option_trade_legs (option_trade_id, leg_type, side, strike_price, expiry_date, premium)
                VALUES (:option_trade_id, :leg_type, :side, :strike_price, :expiry_date, :premium)
                """),
                leg_rows,
            )
        session.commit()
    clear_cache_selective(["options"])


@st.cache_data(ttl=Config.CACHE_TTL["option_trades"], show_spinner=False)
def _load_all_option_trade_legs() -> List[Dict[str, Any]]:
    """Load all option trade legs in a single cached query."""
    conn = get_st_connection()
    with conn.session as session:
        result = session.execute(text("""
            SELECT id, option_trade_id, leg_type, side, strike_price,
                   expiry_date, premium, close_premium
            FROM option_trade_legs
            ORDER BY option_trade_id, id
        """))
        rows = result.fetchall()
        columns = [
            "id", "option_trade_id", "leg_type", "side", "strike_price",
            "expiry_date", "premium", "close_premium",
        ]
        return [dict(zip(columns, row)) for row in rows]


register_cache("options", _load_all_option_trade_legs)


def load_option_trade_legs(option_trade_id: Optional[int] = None) -> List[Dict[str, Any]]:
    """Load option trade legs from the single cached query, filtering in memory when needed."""
    try:
        all_legs = _load_all_option_trade_legs()
        if option_trade_id is not None:
            return [leg for leg in all_legs if leg.get("option_trade_id") == option_trade_id]
        return all_legs
    except Exception as e:
        st.error(f"Database error loading legs: {e}")
        return []


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
            params,
        )
        session.commit()
    clear_cache_selective(["options"])


@st.cache_data(ttl=Config.CACHE_TTL["option_trades"], show_spinner=False)
def _load_all_option_trades() -> List[Dict[str, Any]]:
    """Load all option trades in a single cached query to avoid repeated per-status scans."""
    conn = get_st_connection()
    with conn.session as session:
        result = session.execute(text("""
            SELECT id, ticker, platform_id, strategy, strike_price, expiry_date,
                   trade_date, transaction_type, option_open_price, open_fee,
                   option_close_price, close_fee, profit_loss, status, close_date,
                   notes, quantity
            FROM option_trades
        """))
        rows = result.fetchall()
        columns = [
            "id", "ticker", "platform_id", "strategy", "strike_price", "expiry_date",
            "trade_date", "transaction_type", "option_open_price", "open_fee",
            "option_close_price", "close_fee", "profit_loss", "status", "close_date",
            "notes", "quantity",
        ]
        return [dict(zip(columns, row)) for row in rows]


register_cache("options", _load_all_option_trades)


def load_option_trades(status: Optional[Any] = None) -> List[Dict[str, Any]]:
    """Load option trades from the single cached query, filtering by status in memory."""
    all_trades = _load_all_option_trades()
    if status is None:
        return all_trades
    if isinstance(status, (list, tuple, set)):
        allowed = set(status)
        return [t for t in all_trades if t.get("status") in allowed]
    return [t for t in all_trades if t.get("status") == status]


@st.cache_data(ttl=Config.CACHE_TTL["trades"], show_spinner=False)
def load_all_trades() -> List[Dict[str, Any]]:
    """Load all raw trades from the trades table.

    Used by the wash-sale detection engine to find replacement stock buys
    within the 30-day window around a loss sale.
    """
    conn = get_st_connection()
    with conn.session as session:
        result = session.execute(text("""
            SELECT id, ticker, platform_id, price, quantity, date, trade_type, direction
            FROM trades
            ORDER BY date, id
        """))
        rows = result.fetchall()
        columns = ["id", "ticker", "platform_id", "price", "quantity", "date", "trade_type", "direction"]
        return [dict(zip(columns, row)) for row in rows]


register_cache("trades", load_all_trades)


def close_option_trade(trade_id, status, close_date, option_close_price, notes=None, close_fee=0):
    conn = get_st_connection()
    with conn.session as session:
        # Get transaction_type, option_open_price, open_fee, quantity for this trade
        result = session.execute(
            text("SELECT transaction_type, option_open_price, open_fee, COALESCE(quantity, 1) FROM option_trades WHERE id = :trade_id"),
            {"trade_id": trade_id},
        )
        row = result.fetchone()
        if row:
            transaction_type, option_open_price, open_fee, quantity = row
            option_open_price = float(option_open_price) if option_open_price is not None else 0.0
            option_close_price = float(option_close_price) if option_close_price is not None else 0.0
            open_fee = float(open_fee) if open_fee is not None else 0.0
            close_fee = float(close_fee) if close_fee is not None else 0.0
            quantity = int(quantity) if quantity is not None else 1
            total_fee = open_fee + close_fee
            if transaction_type == "credit":
                profit_loss = (option_open_price - option_close_price) * 100 * quantity - total_fee
            else:
                profit_loss = (option_close_price - option_open_price) * 100 * quantity - total_fee
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
            },
        )
        session.commit()
    clear_cache_selective(["options"])


def _position_fingerprint(pos: Dict[str, Any]) -> Tuple[Any, ...]:
    """Create a normalized, hashable comparison tuple for a position row.

    Rounds floats to tolerate PostgreSQL REAL (32-bit float) storage precision so
    unchanged positions are not needlessly deleted and re-inserted during sync.
    """
    def _r(val: Any, digits: int) -> Optional[float]:
        if val is None:
            return None
        try:
            return round(float(val), digits)
        except Exception:
            return None

    def _d(val: Any) -> Optional[str]:
        if val is None:
            return None
        if isinstance(val, datetime.datetime):
            return val.date().isoformat()
        if isinstance(val, datetime.date):
            return val.isoformat()
        return str(val)

    return (
        pos.get("trade_type"),
        pos.get("position_status"),
        _r(pos.get("entry_price"), 4),
        _r(pos.get("quantity"), 4),
        _d(pos.get("entry_date")),
        _r(pos.get("exit_price"), 4),
        _d(pos.get("exit_date")),
        _r(pos.get("profit_loss"), 2),
        pos.get("direction") or "Long",
    )


def sync_positions_from_trades():
    """
    Syncs the positions table with the trades table using FIFO lot matching.

    Memory & bloat optimizations for low-RAM PostgreSQL (e.g., Aiven Free Tier):
    - Diffs computed positions against existing rows per (ticker, platform_id) and
      only deletes/re-inserts keys that actually changed, preventing full-table
      dead-tuple bloat and autovacuum memory spikes.
    - Uses fixed-parameter chunked executemany statements instead of constructing
      a single multi-thousand-parameter SQL string.
    """
    conn = get_st_connection()
    with conn.session as session:
        result = session.execute(text("""
            SELECT id, ticker, platform_id, price, quantity, date, trade_type, direction
            FROM trades
            ORDER BY ticker, platform_id, date, id
        """))
        trades = result.fetchall()

        trades_by_key: Dict[Tuple[str, Any], List[Dict[str, Any]]] = defaultdict(list)
        for row in trades:
            _id, ticker, platform_id, price, quantity, date, trade_type, direction = row
            try:
                qty = round(float(quantity), 6)
            except Exception:
                qty = 0.0
            if qty == 0:
                continue
            ttype = (str(trade_type) if trade_type is not None else "").strip().lower()
            tdir = (str(direction) if direction is not None else "Long").strip().capitalize()
            trades_by_key[(ticker, platform_id)].append({
                "id": _id,
                "price": float(price) if price is not None else 0.0,
                "quantity": qty,
                "date": date,
                "trade_type": ttype,
                "direction": tdir,
            })

        # Compute desired positions grouped by (ticker, platform_id)
        desired_closed_by_key: Dict[Tuple[str, Any], List[Dict[str, Any]]] = defaultdict(list)
        desired_open_by_key: Dict[Tuple[str, Any], List[Dict[str, Any]]] = defaultdict(list)

        for (ticker, platform_id), trade_list in trades_by_key.items():
            open_lots: deque = deque()   # Long open lots
            short_lots: deque = deque()  # Short open lots
            for trade in trade_list:
                ttype = trade["trade_type"].lower()
                tdir = trade.get("direction", "Long")

                if tdir == "Short":
                    if ttype == "sell":
                        short_lots.append({
                            "price": trade["price"],
                            "quantity": trade["quantity"],
                            "entry_date": trade["date"],
                            "remaining": round(trade["quantity"], 6),
                        })
                    elif ttype == "buy":
                        cover_qty = round(trade["quantity"], 6)
                        cover_price = trade["price"]
                        cover_date = trade["date"]
                        while round(cover_qty, 6) > 0 and short_lots:
                            lot = short_lots[0]
                            lot_qty = round(lot["remaining"], 6)
                            matched_qty = round(min(lot_qty, cover_qty), 6)
                            profit_loss = round((lot["price"] - cover_price) * matched_qty, 2)
                            desired_closed_by_key[(ticker, platform_id)].append({
                                "ticker": ticker,
                                "trade_type": None,
                                "position_status": "close",
                                "entry_price": lot["price"],
                                "quantity": matched_qty,
                                "entry_date": lot["entry_date"],
                                "exit_price": cover_price,
                                "exit_date": cover_date,
                                "platform_id": platform_id,
                                "profit_loss": profit_loss,
                                "direction": "Short",
                            })
                            lot["remaining"] = round(lot["remaining"] - matched_qty, 6)
                            cover_qty = round(cover_qty - matched_qty, 6)
                            if abs(lot["remaining"]) < 1e-6:
                                short_lots.popleft()
                else:
                    if ttype == "buy":
                        open_lots.append({
                            "price": trade["price"],
                            "quantity": trade["quantity"],
                            "entry_date": trade["date"],
                            "remaining": round(trade["quantity"], 6),
                        })
                    elif ttype == "sell":
                        sell_qty = round(trade["quantity"], 6)
                        sell_price = trade["price"]
                        sell_date = trade["date"]
                        while round(sell_qty, 6) > 0 and open_lots:
                            lot = open_lots[0]
                            lot_qty = round(lot["remaining"], 6)
                            matched_qty = round(min(lot_qty, sell_qty), 6)
                            profit_loss = round((sell_price - lot["price"]) * matched_qty, 2)
                            desired_closed_by_key[(ticker, platform_id)].append({
                                "ticker": ticker,
                                "trade_type": None,
                                "position_status": "close",
                                "entry_price": lot["price"],
                                "quantity": matched_qty,
                                "entry_date": lot["entry_date"],
                                "exit_price": sell_price,
                                "exit_date": sell_date,
                                "platform_id": platform_id,
                                "profit_loss": profit_loss,
                                "direction": "Long",
                            })
                            lot["remaining"] = round(lot["remaining"] - matched_qty, 6)
                            sell_qty = round(sell_qty - matched_qty, 6)
                            if abs(lot["remaining"]) < 1e-6:
                                open_lots.popleft()

            for lot in open_lots:
                desired_open_by_key[(ticker, platform_id)].append({
                    "ticker": ticker,
                    "trade_type": None,
                    "position_status": "open",
                    "entry_price": lot["price"],
                    "quantity": lot["remaining"],
                    "entry_date": lot["entry_date"],
                    "platform_id": platform_id,
                    "profit_loss": None,
                    "direction": "Long",
                })
            for lot in short_lots:
                desired_open_by_key[(ticker, platform_id)].append({
                    "ticker": ticker,
                    "trade_type": None,
                    "position_status": "open",
                    "entry_price": lot["price"],
                    "quantity": lot["remaining"],
                    "entry_date": lot["entry_date"],
                    "platform_id": platform_id,
                    "profit_loss": None,
                    "direction": "Short",
                })

        # Fetch existing positions to diff per (ticker, platform_id) and skip unchanged keys
        existing_res = session.execute(text("""
            SELECT ticker, trade_type, position_status, entry_price, quantity,
                   entry_date, exit_price, exit_date, platform_id, profit_loss, direction
            FROM positions
        """))
        existing_cols = [
            "ticker", "trade_type", "position_status", "entry_price", "quantity",
            "entry_date", "exit_price", "exit_date", "platform_id", "profit_loss", "direction",
        ]
        existing_by_key: Dict[Tuple[str, Any], List[Tuple[Any, ...]]] = defaultdict(list)
        for erow in existing_res.fetchall():
            ed = dict(zip(existing_cols, erow))
            existing_by_key[(ed["ticker"], ed["platform_id"])].append(_position_fingerprint(ed))

        changed_keys: List[Tuple[str, Any]] = []
        closed_to_insert: List[Dict[str, Any]] = []
        open_to_insert: List[Dict[str, Any]] = []

        for key in trades_by_key.keys():
            desired_rows = desired_closed_by_key.get(key, []) + desired_open_by_key.get(key, [])
            desired_fp = sorted(_position_fingerprint(p) for p in desired_rows)
            existing_fp = sorted(existing_by_key.get(key, []))
            if desired_fp != existing_fp:
                changed_keys.append(key)
                closed_to_insert.extend(desired_closed_by_key.get(key, []))
                open_to_insert.extend(desired_open_by_key.get(key, []))

        if changed_keys:
            delete_params = [{"ticker": t, "platform_id": pid} for t, pid in changed_keys]
            _execute_in_chunks(
                session,
                text("DELETE FROM positions WHERE ticker = :ticker AND platform_id = :platform_id"),
                delete_params,
            )

            if closed_to_insert:
                _execute_in_chunks(
                    session,
                    text("""
                        INSERT INTO positions (
                            ticker, trade_type, position_status, entry_price, quantity,
                            entry_date, exit_price, exit_date, platform_id, profit_loss, direction
                        )
                        VALUES (
                            :ticker, :trade_type, :position_status, :entry_price, :quantity,
                            :entry_date, :exit_price, :exit_date, :platform_id, :profit_loss, :direction
                        )
                    """),
                    closed_to_insert,
                )

            if open_to_insert:
                _execute_in_chunks(
                    session,
                    text("""
                        INSERT INTO positions (
                            ticker, trade_type, position_status, entry_price, quantity,
                            entry_date, platform_id, profit_loss, direction
                        )
                        VALUES (
                            :ticker, :trade_type, :position_status, :entry_price, :quantity,
                            :entry_date, :platform_id, :profit_loss, :direction
                        )
                    """),
                    open_to_insert,
                )

            session.commit()

    clear_cache_selective(["positions"])


def insert_trade(
    ticker: str,
    platform_id: int,
    price: float,
    quantity: float,
    date: Any,
    trade_type: str,
    direction: str = "Long",
) -> None:
    """Insert a new trade into the trades table."""
    conn = get_st_connection()
    with conn.session as session:
        session.execute(
            text("""
            INSERT INTO trades (ticker, platform_id, price, quantity, date, trade_type, direction)
            VALUES (:ticker, :platform_id, :price, :quantity, :date, :trade_type, :direction)
            """),
            {
                "ticker": ticker,
                "platform_id": platform_id,
                "price": price,
                "quantity": quantity,
                "date": date,
                "trade_type": trade_type,
                "direction": direction,
            },
        )
        session.commit()
    clear_cache_selective(["trades"])


_ALLOWED_TRADE_COLUMNS = ("ticker", "platform_id", "price", "quantity", "date", "trade_type", "direction")


def bulk_insert_trades(rows: List[Dict[str, Any]]) -> int:
    """Insert multiple trade rows in a single transaction using chunked executemany.

    Avoids opening a new session/transaction per CSV row and keeps PostgreSQL
    memory bounded on low-RAM instances.
    """
    if not rows:
        return 0

    # Group rows by column set (preserving order within each group) so each batch
    # uses a uniform parameterized INSERT statement.
    grouped_rows: Dict[Tuple[str, ...], List[Dict[str, Any]]] = defaultdict(list)
    for row in rows:
        cols = tuple(c for c in _ALLOWED_TRADE_COLUMNS if c in row)
        if not cols:
            continue
        grouped_rows[cols].append({c: row[c] for c in cols})

    inserted = 0
    conn = get_st_connection()
    with conn.session as session:
        for cols, batch in grouped_rows.items():
            placeholders = ", ".join(f":{col}" for col in cols)
            stmt = text(f"INSERT INTO trades ({', '.join(cols)}) VALUES ({placeholders})")
            _execute_in_chunks(session, stmt, batch)
            inserted += len(batch)
        session.commit()

    if inserted > 0:
        clear_cache_selective(["trades"])
    return inserted


# --- Last upload metadata helpers (DB-backed) -----------------------------
def set_last_upload_time(ts: Optional[str] = None) -> None:
    """Persist the last upload timestamp (UTC ISO string) into the DB.

    If ts is None the current UTC time is used. This function assumes the
    `app_metadata` table is present (managed via migrations/schema.sql).
    """
    if ts is None:
        ts = datetime.datetime.utcnow().isoformat()
    try:
        conn = get_st_connection()
        with conn.session as session:
            session.execute(
                text("""
                INSERT INTO app_metadata (key, value) VALUES (:key, :value)
                ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value
                """),
                {"key": "last_csv_upload", "value": ts},
            )
            session.commit()
        clear_cache_selective(["metadata"])
    except Exception as e:
        logger.error(f"Failed to write last upload metadata to DB: {e}")


@st.cache_data(ttl=Config.CACHE_TTL["metadata"], show_spinner=False)
def get_last_upload_time() -> Optional[str]:
    """Return the last upload UTC ISO timestamp as a string from the DB, or None if not set."""
    try:
        conn = get_st_connection()
        with conn.session as session:
            result = session.execute(
                text("SELECT value FROM app_metadata WHERE key = :key"),
                {"key": "last_csv_upload"},
            )
            row = result.fetchone()
            return row[0] if row else None
    except Exception as e:
        logger.error(f"Failed to read last upload metadata from DB: {e}")
        return None


register_cache("metadata", get_last_upload_time)


# --- Cash flows management ---
def insert_cash_flow(
    platform_id: int,
    flow_type: str,
    amount: float,
    flow_date: Any,
    notes: Optional[str] = None,
) -> None:
    """Insert a new cash deposit or withdrawal into the database."""
    conn = get_st_connection()
    with conn.session as session:
        session.execute(
            text("""
            INSERT INTO cash_flows (platform_id, flow_type, amount, flow_date, notes)
            VALUES (:platform_id, :flow_type, :amount, :flow_date, :notes)
            """),
            {
                "platform_id": platform_id,
                "flow_type": flow_type,
                "amount": amount,
                "flow_date": flow_date,
                "notes": notes,
            },
        )
        session.commit()
    clear_cache_selective(["cash"])


@st.cache_data(ttl=Config.CACHE_TTL["cash_flows"], show_spinner=False)
def load_cash_flows() -> List[Dict[str, Any]]:
    """Load all cash flows from the database."""
    conn = get_st_connection()
    with conn.session as session:
        result = session.execute(
            text("SELECT id, platform_id, flow_type, amount, flow_date, notes FROM cash_flows ORDER BY flow_date DESC")
        )
        rows = result.fetchall()
        columns = ["id", "platform_id", "flow_type", "amount", "flow_date", "notes"]
        return [dict(zip(columns, row)) for row in rows]


register_cache("cash", load_cash_flows)


@st.cache_data(ttl=Config.CACHE_TTL["cash_flows"], show_spinner=False)
def get_total_cash_by_platform() -> Dict[str, float]:
    """Get total cash (deposits - withdrawals) by platform."""
    conn = get_st_connection()
    with conn.session as session:
        result = session.execute(text("""
            SELECT p.name, COALESCE(SUM(CASE WHEN cf.flow_type = 'deposit' THEN cf.amount ELSE -cf.amount END), 0) as total_cash
            FROM platforms p
            LEFT JOIN cash_flows cf ON p.id = cf.platform_id
            GROUP BY p.id, p.name
            ORDER BY p.name
        """))
        rows = result.fetchall()
        return {row[0]: float(row[1]) for row in rows}


register_cache("cash", get_total_cash_by_platform)


# -- Platform-level cash helpers ------------
def set_platform_cash_available(platform_id: int, amount: float) -> None:
    """Update `platforms.cash_available` for a platform and invalidate cash caches."""
    try:
        conn = get_st_connection()
        with conn.session as session:
            session.execute(
                text("UPDATE platforms SET cash_available = :amount WHERE id = :platform_id"),
                {"amount": float(amount), "platform_id": platform_id},
            )
            session.commit()
        clear_cache_selective(["cash"])
    except Exception as e:
        logger.error(f"Failed to set platform cash_available: {e}")
        raise


@st.cache_data(ttl=Config.CACHE_TTL["cash_flows"], show_spinner=False)
def get_platform_cash_available_map() -> Dict[str, float]:
    """Return a mapping {platform_name: cash_available} (0.0 if null or missing)."""
    try:
        conn = get_st_connection()
        with conn.session as session:
            result = session.execute(text("SELECT name, COALESCE(cash_available, 0) FROM platforms ORDER BY name"))
            rows = result.fetchall()
            return {row[0]: float(row[1]) for row in rows}
    except Exception as e:
        logger.error(f"Failed to read platform cash_available: {e}")
        return {}


register_cache("cash", get_platform_cash_available_map)
