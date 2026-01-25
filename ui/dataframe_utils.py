"""DataFrame optimization utilities for memory efficiency."""

import pandas as pd
import numpy as np
from typing import Any, Dict, List, Optional
import logging

logger = logging.getLogger(__name__)

def optimize_dataframe(df: pd.DataFrame, categorical_threshold: float = 0.5) -> pd.DataFrame:
    """Optimize DataFrame memory usage by downcasting numeric types and converting strings to categorical.
    
    Args:
        df: DataFrame to optimize
        categorical_threshold: Ratio of unique values to total values below which to convert to categorical
        
    Returns:
        Optimized DataFrame with reduced memory footprint
    """
    if df.empty:
        return df
    
    optimized_df = df.copy()
    original_memory = optimized_df.memory_usage(deep=True).sum() / 1024**2  # MB
    
    # Optimize numeric columns
    for col in optimized_df.select_dtypes(include=['int64']).columns:
        col_data = optimized_df[col]
        if col_data.min() >= 0:  # Non-negative integers
            if col_data.max() < 255:
                optimized_df[col] = col_data.astype('uint8')
            elif col_data.max() < 65535:
                optimized_df[col] = col_data.astype('uint16')
            elif col_data.max() < 4294967295:
                optimized_df[col] = col_data.astype('uint32')
        else:  # Can be negative
            if col_data.min() >= -128 and col_data.max() <= 127:
                optimized_df[col] = col_data.astype('int8')
            elif col_data.min() >= -32768 and col_data.max() <= 32767:
                optimized_df[col] = col_data.astype('int16')
            elif col_data.min() >= -2147483648 and col_data.max() <= 2147483647:
                optimized_df[col] = col_data.astype('int32')
    
    # Optimize float columns
    for col in optimized_df.select_dtypes(include=['float64']).columns:
        col_data = optimized_df[col]
        # Check if we can downcast to float32 without losing precision needed for financial data
        if col_data.notna().any():
            # Test if float32 precision is sufficient (4 decimal places for financial data)
            test_float32 = col_data.astype('float32')
            if np.allclose(col_data.dropna(), test_float32.dropna(), rtol=1e-4):
                optimized_df[col] = test_float32
    
    # Convert string columns to categorical where beneficial
    for col in optimized_df.select_dtypes(include=['object']).columns:
        col_data = optimized_df[col]
        if not col_data.empty and len(col_data.unique()) / len(col_data) < categorical_threshold:
            try:
                optimized_df[col] = col_data.astype('category')
            except Exception as e:
                logger.warning(f"Could not convert column {col} to categorical: {e}")
    
    # Convert datetime columns to more efficient format if needed
    for col in optimized_df.select_dtypes(include=['datetime64[ns]']).columns:
        # Already optimal, just ensure no object dtype
        if optimized_df[col].dtype == 'object':
            try:
                optimized_df[col] = pd.to_datetime(optimized_df[col])
            except Exception as e:
                logger.warning(f"Could not convert column {col} to datetime: {e}")
    
    optimized_memory = optimized_df.memory_usage(deep=True).sum() / 1024**2  # MB
    memory_reduction = (original_memory - optimized_memory) / original_memory * 100
    
    if memory_reduction > 5:  # Only log significant reductions
        logger.info(f"DataFrame optimization reduced memory from {original_memory:.2f}MB to {optimized_memory:.2f}MB ({memory_reduction:.1f}% reduction)")
    
    return optimized_df

def get_paginated_data(df: pd.DataFrame, page: int = 1, page_size: int = 100) -> pd.DataFrame:
    """Get a paginated subset of DataFrame data.
    
    Args:
        df: Source DataFrame
        page: Page number (1-indexed)
        page_size: Number of rows per page
        
    Returns:
        Paginated DataFrame subset
    """
    if df.empty:
        return df
    
    start_idx = (page - 1) * page_size
    end_idx = start_idx + page_size
    
    return df.iloc[start_idx:end_idx].copy()

def get_dataframe_info(df: pd.DataFrame) -> Dict[str, Any]:
    """Get comprehensive information about a DataFrame for debugging and monitoring.
    
    Args:
        df: DataFrame to analyze
        
    Returns:
        Dictionary with DataFrame statistics
    """
    if df.empty:
        return {
            'rows': 0,
            'columns': 0,
            'memory_mb': 0,
            'dtypes': {},
            'null_counts': {},
            'memory_by_column': {}
        }
    
    return {
        'rows': len(df),
        'columns': len(df.columns),
        'memory_mb': df.memory_usage(deep=True).sum() / 1024**2,
        'dtypes': df.dtypes.to_dict(),
        'null_counts': df.isnull().sum().to_dict(),
        'memory_by_column': (df.memory_usage(deep=True) / 1024**2).to_dict()
    }

def safe_float_conversion(series: pd.Series, decimals: int = 4) -> pd.Series:
    """Safely convert series to float with specified decimal precision.
    
    Args:
        series: pandas Series to convert
        decimals: Number of decimal places to keep
        
    Returns:
        Converted Series with float dtype
    """
    try:
        return pd.to_numeric(series, errors='coerce').round(decimals)
    except Exception as e:
        logger.warning(f"Error converting series to float: {e}")
        return series

def validate_financial_data(df: pd.DataFrame, 
                          price_columns: Optional[List[str]] = None,
                          quantity_columns: Optional[List[str]] = None) -> Dict[str, List[str]]:
    """Validate financial data for common issues.
    
    Args:
        df: DataFrame to validate
        price_columns: List of column names that should contain prices
        quantity_columns: List of column names that should contain quantities
        
    Returns:
        Dictionary with validation errors by category
    """
    errors = {
        'negative_prices': [],
        'zero_quantities': [],
        'null_values': [],
        'invalid_dates': []
    }
    
    if df.empty:
        return errors
    
    # Check for negative prices
    if price_columns:
        for col in price_columns:
            if col in df.columns:
                negative_mask = (df[col] < 0) & df[col].notna()
                if negative_mask.any():
                    errors['negative_prices'].append(f"{col}: {negative_mask.sum()} negative values")
    
    # Check for zero quantities (might indicate data issues)
    if quantity_columns:
        for col in quantity_columns:
            if col in df.columns:
                zero_mask = df[col] == 0
                if zero_mask.any():
                    errors['zero_quantities'].append(f"{col}: {zero_mask.sum()} zero values")
    
    # Check for null values in critical columns
    critical_cols = (price_columns or []) + (quantity_columns or [])
    for col in critical_cols:
        if col in df.columns:
            null_count = df[col].isnull().sum()
            if null_count > 0:
                errors['null_values'].append(f"{col}: {null_count} null values")
    
    # Check date columns
    date_cols = df.select_dtypes(include=['datetime64']).columns
    for col in date_cols:
        if df[col].isnull().any():
            errors['invalid_dates'].append(f"{col}: contains null dates")
    
    return errors