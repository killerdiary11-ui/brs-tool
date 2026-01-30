import streamlit as st
import pandas as pd
import io

st.set_page_config(page_title="Auto-BRS Tool", layout="wide")
st.title("🏦 Automatic Bank Reconciliation System")

# --- 1. ROBUST FILE LOADER ---
def load_smart(uploaded_file):
    try:
        # METHOD A: For CSV Files (HDFC often comes as CSV)
        if uploaded_file.name.lower().endswith('.csv'):
            # Read raw text first to avoid "ParserError" on junk rows
            content = uploaded_file.getvalue().decode("utf-8", errors='ignore')
            lines = content.splitlines()
            
            # Find the row number where "Date" appears
            skip_rows = 0
            for i, line in enumerate(lines[:50]): # Check first 50 lines
                if "Date" in line and ("Narration" in line or "Vch" in line):
                    skip_rows = i
                    break
            
            # Reset file pointer and read with that skip
            uploaded_file.seek(0)
            return pd.read_csv(uploaded_file, skiprows=skip_rows)
            
        # METHOD B: For Excel Files (.xlsx)
        else:
            return pd.read_excel(uploaded_file)

    except Exception as e:
        st.error(f"Error reading file: {e}")
        return None

# --- 2. UPLOAD SECTION ---
col1, col2 = st.columns(2)
with col1:
    bank_file = st.file_uploader("📂 Upload Bank Statement", type=['csv', 'xlsx', 'xls'])
with col2:
    busy_file = st.file_uploader("📂 Upload Busy Ledger", type=['csv', 'xlsx', 'xls'])

if bank_file and busy_file:
    st.divider()
    st.write("Running Reconciliation...")

    # Load Files
    bank_df = load_smart(bank_file)
    busy_df = load_smart(busy_file)

    if bank_df is not None and busy_df is not None:
        try:
            # --- 3. CLEAN & MATCH ---
            # Helper to clean numbers (remove commas, handle NaNs)
            def clean(x): 
                return pd.to_numeric(str(x).replace(',', '').replace('nan',''), errors='coerce')

            # Clean Bank
            # Find the header row usually puts "Date" in columns. 
            # If HDFC has weird headers, we ensure we rename or find the right cols.
            # (This logic assumes standard column names exist after skip)
            bank_df = bank_df.dropna(subset=['Date'])
            bank_df['Net'] = clean(bank_df['Deposit Amt.']).fillna(0) - clean(bank_df['Withdrawal Amt.']).fillna(0)

            # Clean Busy
            busy_df = busy_df.dropna(subset=['Date'])
            busy_df['Net'] = clean(busy_df['Debit(Rs.)']).fillna(0) - clean(busy_df['Credit(Rs.)']).fillna(0)

            # Sequence Matching (The Logic)
            bank_df['Key'] = bank_df['Net'].round(2).astype(str) + "_" + bank_df.groupby('Net').cumcount().astype(str)
            busy_df['Key'] = busy_df['Net'].round(2).astype(str) + "_" + busy_df.groupby('Net').cumcount().astype(str)

            bank_keys = set(bank_df['Key'])
            busy_keys = set(busy_df['Key'])

            # --- 4. RESULTS ---
            missing_in_busy = bank_df[~bank_df['Key'].isin(busy_keys)]
            missing_in_bank = busy_df[~busy_df['Key'].isin(bank_keys)]

            st.success("Reconciliation Complete!")
            
            c1, c2 = st.columns(2)
            with c1:
                st.subheader("❌ Missing in Busy")
                st.write(f"Entries: {len(missing_in_busy)}")
                st.dataframe(missing_in_busy)
                st.download_button("Download CSV", missing_in_busy.to_csv(index=False), "Missing_In_Busy.csv")
            
            with c2:
                st.subheader("❌ Unpresented Cheques")
                st.write(f"Entries: {len(missing_in_bank)}")
                st.dataframe(missing_in_bank)
                st.download_button("Download CSV", missing_in_bank.to_csv(index=False), "Unpresented_Cheques.csv")

        except Exception as e:
            st.error(f"Processing Error: {e}")
            st.write("Tip: Check if your columns are named 'Date', 'Deposit Amt.', 'Withdrawal Amt.' (Bank) and 'Debit(Rs.)', 'Credit(Rs.)' (Busy).")
