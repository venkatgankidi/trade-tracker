"""Shared utility functions for the trade tracker UI."""
import pandas as pd
from typing import Dict, List
from db.db_utils import PLATFORM_CACHE


def color_profit_loss(val):
    """Color code profit/loss values: green for positive, red for negative."""
    try:
        v = float(str(val).replace('%', ''))
    except:
        return ""
    color = "green" if v > 0 else ("red" if v < 0 else "black")
    return f"color: {color}"


def get_platform_id_to_name_map() -> Dict[int, str]:
    """Get a mapping of platform IDs to their names."""
    return {v: k for k, v in PLATFORM_CACHE.cache.items()}


def apply_profit_loss_styling(df: pd.DataFrame, cols: List[str]):
    """Apply profit/loss styling to specified columns in a DataFrame.
    
    Args:
        df: The DataFrame to style
        cols: List of column names to apply styling to
        
    Returns:
        Styled DataFrame if columns exist, otherwise returns the DataFrame as-is
    """
    if cols:
        return df.style.map(color_profit_loss, subset=cols)
    return df
