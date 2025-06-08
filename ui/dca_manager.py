import streamlit as st
from ui.portfolio_report import portfolio_report
from ui.trade_form import trade_form
from ui.csv_upload import upload_csv

def dca_manager():
    st.header("DCA Manager")
    portfolio_report()
    st.subheader("Manual Trade Entry")
    trade_form()
    st.subheader("CSV Upload")
    upload_csv()
