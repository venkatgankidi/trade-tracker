import streamlit as st
import csv
import json
import tempfile
from db.db_utils import PLATFORM_CACHE, set_last_upload_time
from sqlalchemy import text
from typing import Optional, List, Dict, Any

def upload_csv() -> None:
    """
    Streamlit UI for uploading trades via CSV. Validates file and mapping, and inserts trades into the database.
    """
    platform_type: str = st.selectbox("Select Platform Type", list(PLATFORM_CACHE.keys()))
    uploaded_file = st.file_uploader("Choose a file", type=["csv"])
    if uploaded_file:
        with tempfile.NamedTemporaryFile(delete=False, suffix=".csv") as tmp_file:
            tmp_file.write(uploaded_file.read())
            tmp_path = tmp_file.name
        try:
            with open("config/mapping_config.json", "r") as config_file:
                mappings = json.load(config_file)
            column_mapping = mappings.get(platform_type, mappings["OTHER"])
        except Exception as e:
            st.error(f"Error loading mapping config: {e}")
            return
        if st.button("Submit"):
            try:
                conn = st.connection("postgresql", type="sql")
                rows: List[Dict[str, Any]] = []
                with open(tmp_path, "r") as file:
                    reader = csv.DictReader(file)
                    for row in reader:
                        mapped_row = {column_mapping[k]: v for k, v in row.items() if k in column_mapping and column_mapping[k]}
                        # Validate required fields
                        if not mapped_row.get("ticker") or not mapped_row.get("date"):
                            continue
                        mapped_row["platform_id"] = mapped_row.get("platform_id") if platform_type == "OTHER" else PLATFORM_CACHE.get(platform_type)
                        rows.append(mapped_row)
                if not rows:
                    st.warning("No valid rows found in the uploaded file.")
                    return
                for row in rows:
                    columns = list(row.keys())
                    placeholders = ", ".join([f":{col}" for col in columns])
                    sql = text(f"INSERT INTO trades ({', '.join(columns)}) VALUES ({placeholders})")
                    with conn.session as session:
                        session.execute(sql, row)
                        session.commit()
                st.success("Trades uploaded successfully!")
                # Record the upload time (UTC)
                try:
                    set_last_upload_time()
                except Exception:
                    # non-fatal: don't block user on metadata write
                    pass
                st.rerun()
            except Exception as e:
                st.error(f"Error uploading trades: {e}")
