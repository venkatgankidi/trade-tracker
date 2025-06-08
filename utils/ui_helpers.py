import streamlit as st

def render_table(data, columns=None, title=None):
    """
    Render a table with optional title and columns.
    """
    if title:
        st.subheader(title)
    if not data:
        st.write("No data found.")
        return
    if columns:
        st.table([{col: row.get(col, "") for col in columns} for row in data])
    else:
        st.table(data)

def show_success(message, delay=3):
    st.success(message)
    import time
    time.sleep(delay)
    st.rerun()

def show_error(message, delay=3):
    st.error(message)
    import time
    time.sleep(delay)
    st.rerun()
