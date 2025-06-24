import streamlit as st
from db.db_utils import PLATFORM_CACHE
from sqlalchemy import text
from typing import Optional

# Default values for the form fields
defaults = {
    "ticker": "",
    "platform": list(PLATFORM_CACHE.keys())[0] if PLATFORM_CACHE else "",
    "price": 0.0,
    "quantity": 0.0,
    "date": None,
    "trade_type": "Buy",
}

def trade_form() -> None:
    """
    Streamlit form for manual trade entry. Validates user input and inserts trade into the database.
    """
    # Initialize session state for form fields
    for key, value in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = value

    with st.form("trade_form"):
        ticker: str = st.text_input("Ticker", value=st.session_state["ticker"], key="ticker")
        platform: str = st.selectbox("Platform", list(PLATFORM_CACHE.keys()), index=list(PLATFORM_CACHE.keys()).index(st.session_state["platform"]) if st.session_state["platform"] in PLATFORM_CACHE else 0, key="platform")
        price: float = st.number_input("Price", min_value=0.0, format="%.2f", value=st.session_state["price"], key="price")
        quantity: float = st.number_input("Quantity", min_value=0.0, format="%.5f", value=st.session_state["quantity"], key="quantity")
        date = st.date_input("Date", value=st.session_state["date"] or None, key="date")
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
                # Reset form values to defaults
                for key, value in defaults.items():
                    st.session_state[key] = value
                st.rerun()
            except Exception as e:
                st.error(f"Error adding trade: {e}")
