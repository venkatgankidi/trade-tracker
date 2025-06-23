import streamlit as st
from db.db_utils import PLATFORM_CACHE
from sqlalchemy import text
from typing import Optional

def trade_form() -> None:
    """
    Streamlit form for manual trade entry. Validates user input and inserts trade into the database.
    """
    with st.form("trade_form"):
        ticker: str = st.text_input("Ticker")
        platform: str = st.selectbox("Platform", list(PLATFORM_CACHE.keys()))
        purchase_price: float = st.number_input("Purchase Price", min_value=0.0, format="%.2f")
        purchase_quantity: float = st.number_input("Purchase Quantity", min_value=0.0, format="%.5f")
        date = st.date_input("Date")
        trade_type: str = st.selectbox("Trade Type", ["Buy", "Sell"])
        submit_button = st.form_submit_button("Submit Trade")
        error_msgs = []
        if submit_button:
            if not ticker.strip():
                error_msgs.append("Ticker cannot be empty.")
            if purchase_price <= 0 or purchase_quantity <= 0:
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
                "price": purchase_price,
                "quantity": purchase_quantity,
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
                st.rerun()
            except Exception as e:
                st.error(f"Error adding trade: {e}")
