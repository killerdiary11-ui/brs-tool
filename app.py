import streamlit as st
import pandas as pd
import io

st.set_page_config(page_title="Auto-BRS Tool", layout="wide")
st.title("🏦 Automatic Bank Reconciliation System")
st.markdown("### Upload HDFC Statement & Busy Ledger")

# --- 1. UPLOAD SECTION ---
col1, col2 = st.columns(2)
with col1:
    bank_file = st.file_uploader("📂 Upload Bank Statement", type=['csv', 'xlsx'])
with col2:
    busy_file = st.file_uploader("📂 Upload Busy Ledger", type=['csv', 'xlsx'])

if bank_file and busy_file:
    st.divider()
    st.write("Running Reconciliation...")

    try:
        # --- 2. SMART LOADER ---
        def load_smart(uploaded_file):
            # Read first 30 lines to find header
            if uploaded_file.name.endswith('.csv'):
                preview = pd.read_csv(uploaded_file, nrows=30, header=None)
            else:
                preview = pd.read_excel(uploaded_file, nrows=30, header=None)
            
            # Find row with 'Date'
            header_row = -1
            for i, row in preview.iterrows():
                if "Date" in str(row.values):
                    header_row = i
                    break
            
            # Reset pointer
            uploaded_file.seek(0)
            
            if uploaded_file.name.endswith('.csv'):
                return pd.read_csv(uploaded_file, skiprows=header_row)
            else:
                return pd.read_excel(uploaded_file, skiprows=header_row)

        bank_df = load_smart(bank_file)
        busy_df = load_smart(busy_file)

        # --- 3. CLEAN & CALCULATE ---
        def clean(x): return pd.to_numeric(str(x).replace(',', '').replace('nan',''), errors='coerce')

        bank_df = bank_df.dropna(subset=['Date'])
        bank_df['Net'] = clean(bank_df['Deposit Amt.']).fillna(0) - clean(bank_df['Withdrawal Amt.']).fillna(0)

        busy_df = busy_df.dropna(subset=['Date'])
        busy_df['Net'] = clean(busy_df['Debit(Rs.)']).fillna(0) - clean(busy_df['Credit(Rs.)']).fillna(0)

        # --- 4. MATCHING LOGIC (Sequence Match) ---
        bank_df['Key'] = bank_df['Net'].round(2).astype(str) + "_" + bank_df.groupby('Net').cumcount().astype(str)
        busy_df['Key'] = busy_df['Net'].round(2).astype(str) + "_" + busy_df.groupby('Net').cumcount().astype(str)

        bank_keys = set(bank_df['Key'])
        busy_keys = set(busy_df['Key'])

        # --- 5. RESULTS ---
        missing_in_busy = bank_df[~bank_df['Key'].isin(busy_keys)]
        missing_in_bank = busy_df[~busy_df['Key'].isin(bank_keys)]

        col1, col2 = st.columns(2)
        with col1:
            st.error(f"Missing in Busy: {len(missing_in_busy)}")
            st.dataframe(missing_in_busy)
            st.download_button("Download CSV", missing_in_busy.to_csv(index=False), "Missing_In_Busy.csv")

        with col2:
            st.warning(f"Unpresented Cheques: {len(missing_in_bank)}")
            st.dataframe(missing_in_bank)
            st.download_button("Download CSV", missing_in_bank.to_csv(index=False), "Unpresented_Cheques.csv")

    except Exception as e:
        st.error(f"Error: {e}")
