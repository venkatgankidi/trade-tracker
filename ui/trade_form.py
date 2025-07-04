import streamlit as st
from db.db_utils import PLATFORM_CACHE, load_platforms
from sqlalchemy import text
from typing import Optional

# Default values for the form fields
defaults = {
    "ticker": "",
    "platform": "",
    "price": 0.0,
    "quantity": 0.0,
    "date": None,
    "trade_type": "Buy",
}

def trade_form() -> None:
    """
    Streamlit form for manual trade entry. Validates user input and inserts trade into the database.
    """
    # Always load platforms before using PLATFORM_CACHE
    load_platforms()
    # Initialize session state for form fields
    for key, value in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = value

    platform_keys = PLATFORM_CACHE.keys()
    if not platform_keys:
        st.warning("No platforms available. Please configure platforms in the database.")
        return

    with st.form("trade_form"):
        ticker: str = st.text_input("Ticker", key="ticker")
        platform: str = st.selectbox("Platform", platform_keys, index=platform_keys.index(st.session_state["platform"]) if st.session_state["platform"] in platform_keys else 0, key="platform")
        price: float = st.number_input("Price", min_value=0.0, format="%.2f", key="price")
        quantity: float = st.number_input("Quantity", min_value=0.0, format="%.5f", key="quantity")
        date = st.date_input("Date", key="date")
        trade_type: str = st.selectbox("Trade Type", ["Buy", "Sell"], index=["Buy", "Sell"].index(st.session_state["trade_type"]) if st.session_state["trade_type"] in ["Buy", "Sell"] else 0, key="trade_type")
        submit_button = st.form_submit_button("Submit Trade")
        error_msgs = []
        if submit_button:
            if not ticker.strip():
                error_msgs.append("Ticker cannot be empty.")
            if price <= 0 or quantity <= 0:
                error_msgs.append("Price and quantity must be greater than zero.")
            platform_id: Optional[int] = PLATFORM_CACHE.get(platform)
            if platform_id is None:
                error_msgs.append("Invalid platform selected.")
            if error_msgs:
                for msg in error_msgs:
                    st.warning(msg)
                return
            trade_data = {
                "ticker": ticker.strip().upper(),
                "platform_id": platform_id,
                "price": price,
                "quantity": quantity,
                "date": date,
                "trade_type": trade_type,
            }
            try:
                conn = st.connection("postgresql", type="sql")
                columns = list(trade_data.keys())
                placeholders = ", ".join([f":{col}" for col in columns])
                sql = text(f"INSERT INTO trades ({', '.join(columns)}) VALUES ({placeholders})")
                with conn.session as session:
                    session.execute(sql, trade_data)
                    session.commit()
                st.success("Trade added successfully!")
                # Reset form values to defaults by deleting keys
                for key in defaults.keys():
                    if key in st.session_state:
                        del st.session_state[key]
                st.rerun()
            except Exception as e:
                st.error(f"Error adding trade: {e}")
