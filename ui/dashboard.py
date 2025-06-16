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
            st.dataframe(pos_mgr_df, use_container_width=True, hide_index=True)
        else:
            st.info("No positions found for summary.")
    st.markdown("---")

    with st.spinner("Loading portfolio summary..."):
        st.subheader("💼 Portfolio Summary")
        summary_df = get_position_summary_with_total()
        if not summary_df.empty:
            st.dataframe(summary_df, use_container_width=True, hide_index=True)
            # Line chart: Portfolio Value and Unrealized Gains by Platform (like taxes graph)
            if 'Platform' in summary_df.columns and 'Total Portfolio Value' in summary_df.columns and 'Total Unrealized Gains' in summary_df.columns:
                plot_df = summary_df[summary_df['Platform'] != 'Total'].copy()
                melted = plot_df.melt(id_vars=['Platform'], value_vars=['Total Portfolio Value', 'Total Unrealized Gains'], var_name='Metric', value_name='Value')
                chart = alt.Chart(melted).mark_line(point=True).encode(
                    x=alt.X('Platform:N', title='Platform', axis=alt.Axis(labelAngle=-45)),
                    y=alt.Y('Value:Q'),
                    color=alt.Color('Metric:N', title='Metric'),
                    tooltip=['Platform', 'Metric', 'Value']
                )
                st.altair_chart(chart, use_container_width=True)
        else:
            st.info("No positions found for summary.")
    st.markdown("---")

    with st.spinner("Loading option trades summary..."):
        st.subheader("📝 Option Trades Summary")
        opt_df = get_option_trades_summary()
        if not opt_df.empty:
            st.dataframe(opt_df, use_container_width=True, hide_index=True)
        else:
            st.info("No option trades found for summary.")
    st.markdown("---")

    with st.spinner("Loading tax summary..."):
        st.subheader("💵 Tax Summary by Year")
        summary_df = tax_summary()
        if not summary_df.empty:
            st.dataframe(summary_df, use_container_width=True, hide_index=True)
            # Line chart: Yearly Gain/Loss and Estimated Tax
            chart = alt.Chart(summary_df).transform_fold(
                ['Total Gain/Loss', 'Total Estimated Tax'],
                as_=['Metric', 'Value']
            ).mark_line(point=True).encode(
                x=alt.X('Tax Year:O'),
                y=alt.Y('Value:Q'),
                color='Metric:N'
            )
            st.altair_chart(chart, use_container_width=True)
        else:
            st.info("No closed trades found for tax summary.")
