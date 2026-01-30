import streamlit as st
import pandas as pd

st.set_page_config(page_title="Auto-BRS Tool", layout="wide")
st.title("🏦 Automatic Bank Reconciliation System")

# --- 1. ROBUST EXCEL LOADER ---
def load_excel_smart(uploaded_file):
    try:
        # Read first 30 rows to find where the actual data starts
        preview = pd.read_excel(uploaded_file, nrows=30, header=None)
        
        # Search for the row containing "Date"
        header_row = -1
        for i, row in preview.iterrows():
            row_str = row.astype(str).str.cat(sep=' ')
            if "Date" in row_str and ("Narration" in row_str or "Vch" in row_str or "Type" in row_str):
                header_row = i
                break
        
        if header_row == -1:
            st.error(f"Could not find a 'Date' column in {uploaded_file.name}. Please check the file.")
            return None

        # Reload the file starting from the correct row
        return pd.read_excel(uploaded_file, skiprows=header_row)

    except Exception as e:
        st.error(f"Error reading {uploaded_file.name}: {e}")
        return None

# --- 2. UPLOAD SECTION ---
col1, col2 = st.columns(2)
with col1:
    bank_file = st.file_uploader("📂 Upload Bank Statement (XLSX)", type=['xlsx', 'xls'])
with col2:
    busy_file = st.file_uploader("📂 Upload Busy Ledger (XLSX)", type=['xlsx', 'xls'])

if bank_file and busy_file:
    st.divider()
    st.write("Processing Files...")

    # Load Files using the Smart Loader
    bank_df = load_excel_smart(bank_file)
    busy_df = load_excel_smart(busy_file)

    if bank_df is not None and busy_df is not None:
        try:
            # --- 3. CLEAN DATA ---
            def clean(x): 
                return pd.to_numeric(str(x).replace(',', '').replace('nan',''), errors='coerce')

            # Clean Bank
            bank_df = bank_df.dropna(subset=['Date'])
            bank_df['Net'] = clean(bank_df['Deposit Amt.']).fillna(0) - clean(bank_df['Withdrawal Amt.']).fillna(0)

            # Clean Busy
            busy_df = busy_df.dropna(subset=['Date'])
            busy_df['Net'] = clean(busy_df['Debit(Rs.)']).fillna(0) - clean(busy_df['Credit(Rs.)']).fillna(0)

            # --- 4. MATCHING LOGIC (Sequence Match) ---
            # Creates unique ID: Amount_1, Amount_2 to handle duplicates
            bank_df['Key'] = bank_df['Net'].round(2).astype(str) + "_" + bank_df.groupby('Net').cumcount().astype(str)
            busy_df['Key'] = busy_df['Net'].round(2).astype(str) + "_" + busy_df.groupby('Net').cumcount().astype(str)

            bank_keys = set(bank_df['Key'])
            busy_keys = set(busy_df['Key'])

            # --- 5. RESULTS ---
            missing_in_busy = bank_df[~bank_df['Key'].isin(busy_keys)]
            missing_in_bank = busy_df[~busy_df['Key'].isin(bank_keys)]

            st.success("Reconciliation Complete!")
            
            c1, c2 = st.columns(2)
            with c1:
                st.subheader("❌ Missing in Busy")
                st.dataframe(missing_in_busy)
            
            with c2:
                st.subheader("❌ Unpresented Cheques")
                st.dataframe(missing_in_bank)

        except Exception as e:
            st.error(f"Processing Error: {e}")
            st.info("Check: Do your Excel files have columns named 'Deposit Amt.' and 'Withdrawal Amt.' (Bank) / 'Debit(Rs.)' and 'Credit(Rs.)' (Busy)?")
