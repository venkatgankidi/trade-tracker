import streamlit as st
import time
from db.db_utils import PLATFORM_CACHE
from sqlalchemy import text

def trade_form():
    with st.form("trade_form"):
        ticker = st.text_input("Ticker")
        platform = st.selectbox("Platform", list(PLATFORM_CACHE.keys()))
        purchase_price = st.number_input("Purchase Price", min_value=0.0, format="%.2f")
        purchase_quantity = st.number_input("Purchase Quantity", min_value=0.0, format="%.5f")
        date = st.date_input("Date")
        trade_type = st.selectbox("Trade Type", ["Buy", "Sell"])
        submit_button = st.form_submit_button("Submit Trade")

        if submit_button:
            platform_id = PLATFORM_CACHE.get(platform)
            trade_data = {
                "ticker": ticker,
                "platform_id": platform_id,
                "purchase_price": purchase_price,
                "purchase_quantity": purchase_quantity,
                "date": date,
                "trade_type": trade_type,
            }
            try:
                conn = st.connection("postgresql", type="sql")
                columns = list(trade_data.keys())
                values = [trade_data[col] for col in columns]
                placeholders = ", ".join(["%s"] * len(columns))
                sql = text(f"INSERT INTO trades ({', '.join(columns)}) VALUES ({placeholders})")
                with conn.session as session:
                    session.execute(sql, values)
                st.success("Trade added successfully!")
            except Exception as e:
                st.error(f"Error adding trade: {e}")
            time.sleep(3)  # Delay to ensure the message is visible
            st.rerun()
