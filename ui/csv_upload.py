import streamlit as st
import csv
import json
import time
import tempfile

def upload_csv():
    from db.db_utils import PLATFORM_CACHE
    platform_type = st.selectbox("Select Platform Type", list(PLATFORM_CACHE.keys()))
    uploaded_file = st.file_uploader("Choose a file", type=["csv"])
    if uploaded_file:
        with tempfile.NamedTemporaryFile(delete=False, suffix=".csv") as tmp_file:
            tmp_file.write(uploaded_file.read())
            tmp_path = tmp_file.name
        with open("config/mapping_config.json", "r") as config_file:
            mappings = json.load(config_file)
            column_mapping = mappings.get(platform_type, mappings["OTHER"])
        if st.button("Submit"):
            try:
                conn = st.connection("postgresql", type="sql")
                with open(tmp_path, "r") as file:
                    reader = csv.DictReader(file)
                    rows = [{column_mapping[k]: v for k, v in row.items() if k in column_mapping} for row in reader]
                    for row in rows:
                        row["platform_id"] = row.get("platform_id") if platform_type == "OTHER" else PLATFORM_CACHE.get(platform_type)
                        columns = list(row.keys())
                        values = [row[col] for col in columns]
                        placeholders = ", ".join(["%s"] * len(columns))
                        sql = f"INSERT INTO trades ({', '.join(columns)}) VALUES ({placeholders})"
                        with conn.session() as session:
                            session.execute(sql, values)
                    print("Mapped Rows:", rows)  # Debugging line to check mapped rows
                    st.success("Trades uploaded successfully!")
            except Exception as e:
                st.error(f"Error uploading trades: {e}")
                print("Error uploading trades:", e)
            time.sleep(3)
            st.rerun()
