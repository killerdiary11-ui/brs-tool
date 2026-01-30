import streamlit as st
import pandas as pd

st.set_page_config(page_title="Auto-BRS Tool", layout="wide")
st.title("🏦 Automatic Bank Reconciliation System")

# --- 1. UNIVERSAL FILE LOADER ---
def load_file_smart(uploaded_file):
    try:
        # A. Determine File Type
        filename = uploaded_file.name.lower()
        
        # B. Read a preview to find the "Header Row" (Row with 'Date')
        if filename.endswith('.csv'):
            # Read raw lines for CSV
            uploaded_file.seek(0)
            preview = pd.read_csv(uploaded_file, nrows=50, header=None, on_bad_lines='skip')
        else:
            # Read excel for XLSX
            preview = pd.read_excel(uploaded_file, nrows=50, header=None)
            
        # C. Find the row index that contains "Date"
        header_row_idx = -1
        for i, row in preview.iterrows():
            row_text = row.astype(str).str.cat(sep=' ').lower()
            if "date" in row_text and ("narration" in row_text or "vch" in row_text or "particulars" in row_text):
                header_row_idx = i
                break
        
        if header_row_idx == -1:
            st.error(f"❌ Could not find a 'Date' column in {uploaded_file.name}. Is this the right file?")
            return None

        # D. Load the full file starting from that header row
        uploaded_file.seek(0) # Reset file pointer
        if filename.endswith('.csv'):
            return pd.read_csv(uploaded_file, skiprows=header_row_idx)
        else:
            return pd.read_excel(uploaded_file, skiprows=header_row_idx)

    except Exception as e:
        st.error(f"Error reading file: {e}")
        return None

# --- 2. UPLOAD SECTION ---
st.info("Upload your files (CSV or Excel supported)")
col1, col2 = st.columns(2)
with col1:
    bank_file = st.file_uploader("📂 Upload Bank Statement", type=['xlsx', 'xls', 'csv'])
with col2:
    busy_file = st.file_uploader("📂 Upload Busy Ledger", type=['xlsx', 'xls', 'csv'])

if bank_file and busy_file:
    st.divider()
    st.write("⚙️ Processing...")

    # Load Files
    bank_df = load_file_smart(bank_file)
    busy_df = load_file_smart(busy_file)

    if bank_df is not None and busy_df is not None:
        try:
            # --- 3. CLEAN & NORMALIZE ---
            def clean(x): 
                return pd.to_numeric(str(x).replace(',', '').replace('nan',''), errors='coerce')

            # Clean Bank
            bank_df = bank_df.dropna(subset=['Date'])
            # HDFC Logic: Deposit - Withdrawal
            bank_df['Net'] = clean(bank_df['Deposit Amt.']).fillna(0) - clean(bank_df['Withdrawal Amt.']).fillna(0)

            # Clean Busy
            busy_df = busy_df.dropna(subset=['Date'])
            # Busy Logic: Debit - Credit
            busy_df['Net'] = clean(busy_df['Debit(Rs.)']).fillna(0) - clean(busy_df['Credit(Rs.)']).fillna(0)

            # --- 4. SEQUENCE MATCHING ---
            # Create Key: "5000.0_1" (Matches 1st 5000 with 1st 5000)
            bank_df['Key'] = bank_df['Net'].round(2).astype(str) + "_" + bank_df.groupby('Net').cumcount().astype(str)
            busy_df['Key'] = busy_df['Net'].round(2).astype(str) + "_" + busy_df.groupby('Net').cumcount().astype(str)

            bank_keys = set(bank_df['Key'])
            busy_keys = set(busy_df['Key'])

            # --- 5. RESULTS ---
            missing_in_busy = bank_df[~bank_df['Key'].isin(busy_keys)]
            missing_in_bank = busy_df[~busy_df['Key'].isin(bank_keys)]

            st.success("✅ Reconciliation Complete!")
            
            t1, t2 = st.tabs(["MISSING IN BUSY", "UNPRESENTED CHEQUES"])
            
            with t1:
                st.write(f"Count: {len(missing_in_busy)}")
                st.dataframe(missing_in_busy)
            
            with t2:
                st.write(f"Count: {len(missing_in_bank)}")
                st.dataframe(missing_in_bank)

        except Exception as e:
            st.error(f"Processing Error: {e}")
            st.warning("Check your column names. Bank needs 'Deposit Amt.'/'Withdrawal Amt.' and Busy needs 'Debit(Rs.)'/'Credit(Rs.)'")
