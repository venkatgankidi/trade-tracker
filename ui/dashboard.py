import streamlit as st
from ui.positions_ui import get_positions_summary
from ui.portfolio_report import get_position_summary_with_total
from ui.option_trades_ui import get_option_trades_summary
from ui.taxes_ui import tax_summary
import altair as alt

def dashboard():
    st.header("📊 Dashboard")

    with st.spinner("Loading positions summary..."):
        st.subheader("📈 Positions Summary")
        pos_mgr_df = get_positions_summary()
        if not pos_mgr_df.empty:
            highlight_cols = [col for col in pos_mgr_df.columns if col.lower() in ["profit_loss", "gain", "total p/l (closed)", "pct_unrealized_gain"]]
            if highlight_cols:
                def color_profit_loss(val):
                    try:
                        v = float(str(val).replace('%',''))
                    except:
                        return ""
                    color = "green" if v > 0 else ("red" if v < 0 else "black")
                    return f"color: {color}"
                styled_df = pos_mgr_df.style.map(color_profit_loss, subset=highlight_cols)
                st.dataframe(styled_df, use_container_width=True, hide_index=True)
            else:
                st.dataframe(pos_mgr_df, use_container_width=True, hide_index=True)
        else:
            st.info("No positions found for summary.")
    st.markdown("---")

    with st.spinner("Loading portfolio summary..."):
        st.subheader("💼 Portfolio Summary")
        summary_df = get_position_summary_with_total()
        if not summary_df.empty:
            highlight_cols = [col for col in summary_df.columns if col.lower() in ["total unrealized gains", "pct unrealized gain"]]
            if highlight_cols:
                def color_profit_loss(val):
                    try:
                        v = float(str(val).replace('%',''))
                    except:
                        return ""
                    color = "green" if v > 0 else ("red" if v < 0 else "black")
                    return f"color: {color}"
                styled_df = summary_df.style.map(color_profit_loss, subset=highlight_cols)
                st.dataframe(styled_df, use_container_width=True, hide_index=True)
            else:
                st.dataframe(summary_df, use_container_width=True, hide_index=True)
        else:
            st.info("No positions found for summary.")
    st.markdown("---")

    with st.spinner("Loading option trades summary..."):
        st.subheader("📝 Option Trades Summary")
        opt_df = get_option_trades_summary()
        if not opt_df.empty:
            highlight_cols = [col for col in opt_df.columns if col.lower() in ["profit_loss", "gain", "total option p/l (closed)"]]
            if highlight_cols:
                def color_profit_loss(val):
                    try:
                        v = float(str(val).replace('%',''))
                    except:
                        return ""
                    color = "green" if v > 0 else ("red" if v < 0 else "black")
                    return f"color: {color}"
                styled_df = opt_df.style.map(color_profit_loss, subset=highlight_cols)
                st.dataframe(styled_df, use_container_width=True, hide_index=True)
            else:
                st.dataframe(opt_df, use_container_width=True, hide_index=True)
        else:
            st.info("No option trades found for summary.")
    st.markdown("---")

    with st.spinner("Loading tax summary..."):
        st.subheader("💵 Tax Summary by Year")
        summary_df = tax_summary()
        if not summary_df.empty:
            highlight_cols = [col for col in summary_df.columns if col.lower() in ["total gain/loss","total estimated tax"]]
            if highlight_cols:
                def color_profit_loss(val):
                    try:
                        v = float(str(val).replace('%',''))
                    except:
                        return ""
                    color = "green" if v > 0 else ("red" if v < 0 else "black")
                    return f"color: {color}"
                styled_df = summary_df.style.map(color_profit_loss, subset=highlight_cols)
                st.dataframe(styled_df, use_container_width=True, hide_index=True)
            else:
                st.dataframe(summary_df, use_container_width=True, hide_index=True)
        else:
            st.info("No closed trades found for tax summary.")
