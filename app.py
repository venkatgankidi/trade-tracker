import streamlit as st
from collections.abc import Mapping
from db.db_utils import load_platforms
from ui.positions_ui import positions_ui
from ui.option_trades_ui import option_trades_ui
from ui.dca_manager import dca_manager
from ui.dashboard import dashboard

st.set_page_config(page_title="Portfolio Tracker", layout="wide")

NAVIGATION = {
    "Dashboard": "📊 Dashboard",
    "DCA Manager": "📈 DCA Manager",
    "Positions Manager": "📒 Positions Manager",
    "Option Trades Manager": "📑 Option Trades Manager"
}

# Credentials are now loaded from Streamlit secrets for better security.
USERNAME = st.secrets.get("auth_username")
PASSWORD = st.secrets.get("auth_password")

# Ensure that the secrets are set in the Streamlit secrets.toml file
if not USERNAME or not PASSWORD:
    st.error("Authentication credentials are not set. Please configure them in the Streamlit secrets.toml file.")
    st.stop()

def main():
    if "authenticated" not in st.session_state:
        st.session_state["authenticated"] = False

    if not st.session_state["authenticated"]:
        st.title("Login")
        username = st.text_input("Username")
        password = st.text_input("Password", type="password")
        if st.button("Login"):
            if username == USERNAME and password == PASSWORD:
                st.session_state["authenticated"] = True
                st.success("Login successful")
                st.rerun()
            else:
                st.error("Invalid username or password")
        return

    # Sidebar and main app
    with st.sidebar:
        st.markdown(f"**User:** {USERNAME}")
        if st.button("Logout"):
            st.session_state["authenticated"] = False
            st.rerun()

    load_platforms()
    st.sidebar.title("Navigation")
    page = st.sidebar.radio(
        "Go to",
        list(NAVIGATION.keys()),
        format_func=lambda x: NAVIGATION[x]
    )

    if page == "Dashboard":
        dashboard()
    elif page == "DCA Manager":
        dca_manager()
    elif page == "Positions Manager":
        positions_ui()
    elif page == "Option Trades Manager":
        option_trades_ui()

if __name__ == "__main__":
    main()
