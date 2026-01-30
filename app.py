import streamlit as st
import pandas as pd
import io

st.set_page_config(page_title="Auto-BRS Tool", layout="wide")
st.title("🏦 Automatic Bank Reconciliation System")

# --- THE "BRUTE FORCE" FILE LOADER ---
def load_any_file(uploaded_file):
    if uploaded_file is None: return None
    
    df = None
    # 1. Try reading as Excel first (Standard)
    try:
        df = pd.read_excel(uploaded_file)
    except:
        # 2. If that fails, try reading as CSV
        uploaded_file.seek(0)
        try:
            df = pd.read_csv(uploaded_file, on_bad_lines='skip')
        except:
            st.error(f"❌ Could not read {uploaded_file.name}. Is it a valid Excel or CSV file?")
            return None

    # 3. Find the "Date" row automatically
    # This handles the garbage rows at the top of HDFC/Busy files
    header_row = -1
    for i, row in df.head(50).iterrows():
        # Convert row to string and search for "Date"
        row_text = row.astype(str).str.cat(sep=' ').lower()
        if "date" in row_text and ("narration" in row_text or "particulars" in row_text or "vch" in row_text):
            header_row = i
            break
            
    if header_row == -1:
        st.error(f"❌ Could not find a 'Date' column in {uploaded_file.name}.")
        return None

    # 4. Reload the file with the correct header
    uploaded_file.seek(0)
    try:
        if uploaded_file.name.lower().endswith('.csv'):
            return pd.read_csv(uploaded_file, skiprows=header_row+1) # +1 because read_csv counts differently
        else:
            return pd.read_excel(uploaded_file, skiprows=header_row+1)
    except:
        # Fallback: Just slice the dataframe we already have
        new_header = df.iloc[header_row]
        df = df[header_row + 1:]
        df.columns = new_header
        return df

# --- UPLOAD SECTION ---
st.info("Upload your files below. The system will auto-detect HDFC vs Busy.")
col1, col2 = st.columns(2)
with col1:
    f1 = st.file_uploader("📂 Upload File 1", type=['xlsx', 'xls', 'csv'])
with col2:
    f2 = st.file_uploader("📂 Upload File 2", type=['xlsx', 'xls', 'csv'])

if f1 and f2:
    st.divider()
    st.write("⚙️ Processing...")

    # Load both files blindly
    df1 = load_any_file(f1)
    df2 = load_any_file(f2)

    if df1 is not None and df2 is not None:
        try:
            # AUTO-DETECT WHICH IS BANK AND WHICH IS BUSY
            # We check the column names
            bank_df = None
            busy_df = None

            cols1 = str(df1.columns).lower()
            cols2 = str(df2.columns).lower()

            if "deposit" in cols1 or "withdrawal" in cols1:
                bank_df = df1
            elif "debit" in cols1 or "credit" in cols1:
                busy_df = df1
            
            if "deposit" in cols2 or "withdrawal" in cols2:
                bank_df = df2
            elif "debit" in cols2 or "credit" in cols2:
                busy_df = df2

            if bank_df is None or busy_df is None:
                st.error("Could not identify which file is Bank and which is Busy. Check your column headers.")
                st.stop()

            # --- CLEANING & MATCHING ---
            def clean(x): return pd.to_numeric(str(x).replace(',', '').replace('nan',''), errors='coerce')

            # Clean Bank
            bank_df = bank_df.dropna(subset=[bank_df.columns[0]]) # Drop empty rows
            # Find the specific column names for HDFC
            dep_col = [c for c in bank_df.columns if "deposit" in str(c).lower()][0]
            with_col = [c for c in bank_df.columns if "withdrawal" in str(c).lower()][0]
            bank_df['Net'] = clean(bank_df[dep_col]).fillna(0) - clean(bank_df[with_col]).fillna(0)

            # Clean Busy
            busy_df = busy_df.dropna(subset=[busy_df.columns[0]])
            # Find specific column names for Busy
            deb_col = [c for c in busy_df.columns if "debit" in str(c).lower()][0]
            cred_col = [c for c in busy_df.columns if "credit" in str(c).lower()][0]
            busy_df['Net'] = clean(busy_df[deb_col]).fillna(0) - clean(busy_df[cred_col]).fillna(0)

            # SEQUENCE MATCHING
            bank_df['Key'] = bank_df['Net'].round(2).astype(str) + "_" + bank_df.groupby('Net').cumcount().astype(str)
            busy_df['Key'] = busy_df['Net'].round(2).astype(str) + "_" + busy_df.groupby('Net').cumcount().astype(str)

            bank_keys = set(bank_df['Key'])
            busy_keys = set(busy_df['Key'])

            missing_in_busy = bank_df[~bank_df['Key'].isin(busy_keys)]
            missing_in_bank = busy_df[~busy_df['Key'].isin(bank_keys)]

            st.success("✅ Success! Reports generated below.")
            
            t1, t2 = st.tabs(["MISSING IN BUSY", "UNPRESENTED CHEQUES"])
            with t1:
                st.dataframe(missing_in_busy)
            with t2:
                st.dataframe(missing_in_bank)

        except Exception as e:
            st.error(f"Analysis Error: {e}")
