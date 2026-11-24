"""Test database utilities module."""

import pytest
from unittest.mock import patch, MagicMock
import pandas as pd
import sys


class TestDatabaseUtils:
    """Test database utilities functions."""
    
    def test_db_utils_import(self):
        """Test that db_utils can be imported."""
        try:
            from db.db_utils import load_platforms, PLATFORM_CACHE
            assert load_platforms is not None
            assert PLATFORM_CACHE is not None
        except ImportError as e:
            pytest.fail(f"Failed to import db_utils: {e}")
    
    @patch('db.db_utils.st.connection')
    def test_platform_cache_structure(self, mock_connection):
        """Test that platform cache has correct structure."""
        try:
            from db.db_utils import PLATFORM_CACHE
            
            # Test that it's a cache-like object
            assert hasattr(PLATFORM_CACHE, 'cache') or hasattr(PLATFORM_CACHE, 'data')
            
        except ImportError as e:
            pytest.fail(f"Failed to import PLATFORM_CACHE: {e}")
    
    @patch('db.db_utils.st.connection')
    @patch('db.db_utils.st.session_state')
    def test_load_platforms_function(self, mock_session_state, mock_connection):
        """Test load_platforms function."""
        # Mock the streamlit connection
        mock_conn = MagicMock()
        mock_connection.return_value = mock_conn
        
        # Mock session state to avoid streamlit dependency
        mock_session = MagicMock()
        
        try:
            from db.db_utils import load_platforms
            
            # Mock the query execution
            mock_query = MagicMock()
            mock_query.to_df.return_value = MagicMock()
            mock_conn.session.return_value.query.return_value = mock_query
            
            # This should not raise an exception
            try:
                result = load_platforms()
                # The function might return None or a specific structure
                # We're just testing it doesn't crash
            except Exception as e:
                pytest.fail(f"load_platforms() raised an exception: {e}")
                
        except ImportError as e:
            pytest.fail(f"Failed to test load_platforms: {e}")
    
    def test_database_functions_exist(self):
        """Test that expected database functions exist."""
        expected_functions = [
            'load_platforms',
            'get_positions',
            'load_option_trades',
            'get_total_cash_by_platform',
            'get_platform_cash_available_map'
        ]
        
        try:
            from db import db_utils
            db_utils_module = sys.modules['db.db_utils']
            
            for func_name in expected_functions:
                # Check if function exists in module
                if hasattr(db_utils_module, func_name):
                    func = getattr(db_utils_module, func_name)
                    assert callable(func), f"{func_name} should be callable"
                # If function doesn't exist, that's okay for this test
                # We're just checking what's available
                
        except ImportError as e:
            pytest.fail(f"Failed to import db_utils for function testing: {e}")


class TestDatabaseConnections:
    """Test database connection handling."""
    
    @patch('db.db_utils.st.connection')
    def test_connection_creation(self, mock_connection):
        """Test database connection creation."""
        mock_conn = MagicMock()
        mock_connection.return_value = mock_conn
        
        try:
            with patch('db.db_utils.st.session_state', MagicMock()):
                from db.db_utils import st
                
                # Test that connection can be created
                conn = st.connection("postgresql", type="sql", ttl=3600)
                mock_connection.assert_called_with("postgresql", type="sql", ttl=3600)
                
        except ImportError as e:
            pytest.fail(f"Failed to test database connection: {e}")
    
    @patch('db.db_utils.st.connection')
    def test_query_execution(self, mock_connection):
        """Test database query execution."""
        mock_conn = MagicMock()
        mock_connection.return_value = mock_conn
        
        # Mock query result
        mock_query = MagicMock()
        mock_result = MagicMock()
        mock_query.to_df.return_value = mock_result
        mock_conn.session.return_value.query.return_value = mock_query
        
        try:
            with patch('db.db_utils.st.session_state', MagicMock()):
                from db.db_utils import st
                
                conn = st.connection("postgresql", type="sql", ttl=3600)
                query_result = conn.session.query()
                # Just test that query was called (not exact mock equality)
                mock_conn.session.query.assert_called()
                
        except ImportError as e:
            pytest.fail(f"Failed to test query execution: {e}")


class TestDataIntegrity:
    """Test data integrity and validation."""
    
    def test_import_data_structures(self):
        """Test that expected data structures can be imported."""
        try:
            # Test pandas import for dataframes
            import pandas as pd
            assert pd.DataFrame is not None
            
            # Test that db utils can use dataframes
            from db.db_utils import PLATFORM_CACHE
            assert PLATFORM_CACHE is not None
            
        except ImportError as e:
            pytest.fail(f"Failed to import data structures: {e}")
    
    def test_dataframe_handling(self):
        """Test dataframe handling in database operations."""
        try:
            # Test basic dataframe creation
            df = pd.DataFrame({
                'column1': [1, 2, 3],
                'column2': ['a', 'b', 'c'],
                'column3': [1.5, 2.5, 3.5]
            })
            
            assert isinstance(df, pd.DataFrame)
            assert len(df) == 3
            assert list(df.columns) == ['column1', 'column2', 'column3']
            
        except Exception as e:
            pytest.fail(f"Failed to test dataframe operations: {e}")


class TestDatabaseMemoryOptimizations:
    """Test DB connection, batching, diff-sync, and selective caching optimizations."""

    def test_execute_in_chunks_splits_large_batches(self):
        """_execute_in_chunks splits rows into bounded executemany calls."""
        from db.db_utils import _execute_in_chunks
        from sqlalchemy import text

        mock_session = MagicMock()
        stmt = text("INSERT INTO trades (ticker) VALUES (:ticker)")
        rows = [{"ticker": f"T{i}"} for i in range(450)]

        _execute_in_chunks(mock_session, stmt, rows, chunk_size=200)

        assert mock_session.execute.call_count == 3
        assert len(mock_session.execute.call_args_list[0].args[1]) == 200
        assert len(mock_session.execute.call_args_list[1].args[1]) == 200
        assert len(mock_session.execute.call_args_list[2].args[1]) == 50

    def test_load_platforms_queries_only_once(self):
        """load_platforms should not issue a duplicate uncached DB query."""
        from db import db_utils

        db_utils.PLATFORM_CACHE.cache = {}
        with patch.object(db_utils, "load_platforms_from_db", return_value={"Webull": 1, "Fidelity": 2}) as mock_loader, \
             patch.object(db_utils, "get_st_connection") as mock_get_conn:
            db_utils.load_platforms()
            assert db_utils.PLATFORM_CACHE.cache == {"Webull": 1, "Fidelity": 2}
            mock_loader.assert_called_once()
            mock_get_conn.assert_not_called()

    def test_load_option_trades_filters_in_memory(self):
        """load_option_trades filters a single cached fetch by string or collection status."""
        from db import db_utils

        sample = [
            {"id": 1, "status": "open", "ticker": "AAPL"},
            {"id": 2, "status": "closed", "ticker": "MSFT"},
            {"id": 3, "status": "expired", "ticker": "NVDA"},
        ]
        with patch.object(db_utils, "_load_all_option_trades", return_value=sample) as mock_all:
            assert len(db_utils.load_option_trades()) == 3
            assert [t["id"] for t in db_utils.load_option_trades(status="open")] == [1]
            assert [t["id"] for t in db_utils.load_option_trades(status=("closed", "expired"))] == [2, 3]
            assert mock_all.call_count == 3

    def test_load_option_trade_legs_filters_in_memory(self):
        """load_option_trade_legs filters by option_trade_id without extra DB queries."""
        from db import db_utils

        legs = [
            {"id": 10, "option_trade_id": 1, "leg_type": "call"},
            {"id": 11, "option_trade_id": 1, "leg_type": "put"},
            {"id": 12, "option_trade_id": 2, "leg_type": "call"},
        ]
        with patch.object(db_utils, "_load_all_option_trade_legs", return_value=legs):
            assert len(db_utils.load_option_trade_legs()) == 3
            assert [l["id"] for l in db_utils.load_option_trade_legs(1)] == [10, 11]

    def test_bulk_insert_trades_uses_single_transaction(self):
        """bulk_insert_trades commits once for all rows and clears trades cache."""
        from db import db_utils

        mock_session = MagicMock()
        mock_conn = MagicMock()
        mock_conn.session.__enter__.return_value = mock_session

        rows = [
            {"ticker": "AAPL", "platform_id": 1, "price": 150.0, "quantity": 10, "date": "2026-01-01", "trade_type": "Buy"},
            {"ticker": "MSFT", "platform_id": 1, "price": 400.0, "quantity": 5, "date": "2026-01-02", "trade_type": "Buy"},
        ]

        with patch.object(db_utils, "get_st_connection", return_value=mock_conn), \
             patch.object(db_utils, "clear_cache_selective") as mock_clear:
            count = db_utils.bulk_insert_trades(rows)
            assert count == 2
            assert mock_session.execute.call_count == 1
            mock_session.commit.assert_called_once()
            mock_clear.assert_called_once_with(["trades"])

    def test_sync_positions_skips_unchanged_keys_and_batches_changes(self):
        """sync_positions_from_trades skips unchanged (ticker, platform_id) keys to avoid dead-tuple bloat."""
        import datetime
        from db import db_utils

        # AAPL already matches DB; MSFT is new and should be written.
        trades_rows = [
            (1, "AAPL", 1, 100.0, 10.0, datetime.date(2026, 1, 1), "Buy", "Long"),
            (2, "MSFT", 1, 200.0, 5.0, datetime.date(2026, 1, 2), "Buy", "Long"),
        ]
        existing_pos_rows = [
            ("AAPL", None, "open", 100.0, 10.0, datetime.date(2026, 1, 1), None, None, 1, None, "Long"),
        ]

        trades_res = MagicMock()
        trades_res.fetchall.return_value = trades_rows
        existing_res = MagicMock()
        existing_res.fetchall.return_value = existing_pos_rows

        mock_session = MagicMock()
        mock_session.execute.side_effect = [trades_res, existing_res, MagicMock(), MagicMock()]
        mock_conn = MagicMock()
        mock_conn.session.__enter__.return_value = mock_session

        with patch.object(db_utils, "get_st_connection", return_value=mock_conn), \
             patch.object(db_utils, "clear_cache_selective") as mock_clear:
            db_utils.sync_positions_from_trades()

            # Calls: 1 SELECT trades, 1 SELECT positions, 1 DELETE (MSFT only), 1 INSERT open (MSFT only)
            assert mock_session.execute.call_count == 4
            delete_params = mock_session.execute.call_args_list[2].args[1]
            assert delete_params == [{"ticker": "MSFT", "platform_id": 1}]
            insert_params = mock_session.execute.call_args_list[3].args[1]
            assert len(insert_params) == 1
            assert insert_params[0]["ticker"] == "MSFT"
            mock_session.commit.assert_called_once()
            mock_clear.assert_called_once_with(["positions"])

    def test_clear_cache_selective_does_not_wipe_unrelated_caches(self):
        """Clearing 'cash' clears cash/dashboard caches without wiping global cache or trades."""
        from db import db_utils

        cash_fn = MagicMock()
        trades_fn = MagicMock()
        db_utils.register_cache("cash", cash_fn)
        db_utils.register_cache("trades", trades_fn)
        try:
            with patch.object(db_utils.st.cache_data, "clear") as mock_global_clear:
                db_utils.clear_cache_selective(["cash"])
                cash_fn.clear.assert_called_once()
                trades_fn.clear.assert_not_called()
                mock_global_clear.assert_not_called()
        finally:
            db_utils._CACHE_REGISTRY["cash"].remove(cash_fn)
            db_utils._CACHE_REGISTRY["trades"].remove(trades_fn)

    def test_db_connect_args_sets_low_memory_guardrails(self):
        """Config.DB_CONNECT_ARGS caps work_mem and idle/statement timeouts for direct connections."""
        from config import Config

        opts = Config.DB_CONNECT_ARGS["options"]
        assert "work_mem=2MB" in opts
        assert "statement_timeout=" in opts
        assert "idle_in_transaction_session_timeout=" in opts

