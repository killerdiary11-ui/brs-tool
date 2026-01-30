import streamlit as st
import pandas as pd
import numpy as np
import io
from datetime import timedelta

# --- Page Configuration ---
st.set_page_config(page_title="Auto-BRS Tool", layout="wide")

st.title("🏦 Smart Bank Reconciliation System")

# --- Helper Functions ---

def clean_currency(x):
    """Removes commas, 'Dr', 'Cr' and converts to float."""
    if isinstance(x, str):
        clean_str = x.replace(',', '').replace(' Dr', '').replace(' Cr', '').strip()
        try:
            return float(clean_str) if clean_str else 0.0
        except ValueError:
            return 0.0
    return x if x else 0.0

def parse_dates(series):
    """Attempts to convert a column to datetime objects safely."""
    return pd.to_datetime(series, dayfirst=True, errors='coerce')

def load_data(uploaded_file):
    """Smart loader that checks file extension first."""
    if uploaded_file is None:
        return None
        
    filename = uploaded_file.name.lower()
    df_raw = None
    
    try:
        # 1. Strict Excel Check
        if filename.endswith(('.xlsx', '.xls')):
            uploaded_file.seek(0)
            df_raw = pd.read_excel(uploaded_file)
            
        # 2. Strict CSV Check
        elif filename.endswith('.csv'):
            encodings = ['utf-8', 'ISO-8859-1', 'cp1252']
            for enc in encodings:
                try:
                    uploaded_file.seek(0)
                    df_raw = pd.read_csv(uploaded_file, encoding=enc)
                    break
                except:
                    continue
        else:
            st.error("Unsupported file format. Please use .csv or .xlsx")
            return None

    except Exception as e:
        st.error(f"Error loading file: {e}")
        return None

    if df_raw is None:
        st.error("Could not read the file. It might be corrupted or encrypted.")
        return None

    # 3. Find the Header Row (Auto-detection)
    header_idx = -1
    for i, row in df_raw.iterrows():
        row_str = row.astype(str).str.lower().tolist()
        
        # Look for "Date" AND ("Narration" OR "Debit" OR "Credit" OR "Withdraw" OR "Deposit")
        has_date = any("date" in s for s in row_str)
        has_keyword = any(k in s for s in row_str for k in ['narration', 'debit', 'credit', 'withdraw', 'deposit', 'vch', 'particulars'])
        
        if has_date and has_keyword:
            header_idx = i
            break
    
    # 4. Reload with correct header if needed
    if header_idx != -1:
        # If headers are not in the first row, we must reload
        uploaded_file.seek(0)
        if filename.endswith(('.xlsx', '.xls')):
            return pd.read_excel(uploaded_file, header=header_idx+1)
        else:
            # Re-read CSV with identified encoding (assuming 'utf-8' fallback if unknown)
            return pd.read_csv(uploaded_file, header=header_idx+1, encoding='ISO-8859-1') # fallback encoding
    
    return df_raw

# --- Main App Logic ---

with st.sidebar:
    st.header("⚙️ Settings")
    date_tolerance = st.slider("Date Match Window (Days)", 0, 60, 5)

col1, col2 = st.columns(2)

with col1:
    st.subheader("1. Upload Ledger (Book)")
    ledger_file = st.file_uploader("Upload Ledger", type=['csv', 'xlsx', 'xls'], key="ledger")

with col2:
    st.subheader("2. Upload Bank Statement")
    bank_file = st.file_uploader("Upload Bank", type=['csv', 'xlsx', 'xls'], key="bank")

if ledger_file and bank_file:
    st.divider()
    
    # 1. Load Data
    df_book = load_data(ledger_file)
    df_bank = load_data(bank_file)

    if df_book is not None and df_bank is not None:
        
        # --- Preprocessing Ledger (Book) ---
        try:
            df_book.columns = df_book.columns.str.strip()
            cols_lower = [c.lower() for c in df_book.columns]
            
            # Smart Column Mapping
            debit_idx = next((i for i, c in enumerate(cols_lower) if any(x in c for x in ['debit', 'deposit'])), None)
            credit_idx = next((i for i, c in enumerate(cols_lower) if any(x in c for x in ['credit', 'withdraw'])), None)
            date_idx = next((i for i, c in enumerate(cols_lower) if 'date' in c), None)
            
            if debit_idx is None or credit_idx is None:
                st.error("Could not find Amount columns in Ledger. Looked for: Debit/Credit/Deposits/Withdrawals")
                st.write("Columns found:", df_book.columns.tolist())
                st.stop()
            
            debit_col = df_book.columns[debit_idx]
            credit_col = df_book.columns[credit_idx]
            date_col = df_book.columns[date_idx] if date_idx is not None else None
                
            book_clean = df_book.copy()
            book_clean['Debit'] = book_clean[debit_col].apply(clean_currency).fillna(0)
            book_clean['Credit'] = book_clean[credit_col].apply(clean_currency).fillna(0)
            
            if date_col:
                book_clean['Date_Obj'] = parse_dates(book_clean[date_col])
            else:
                book_clean['Date_Obj'] = pd.NaT

            book_clean['Match_Amount'] = book_clean.apply(
                lambda x: x['Debit'] if x['Debit'] > 0 else x['Credit'], axis=1
            )
            book_clean['Type'] = book_clean.apply(
                lambda x: 'Receipt' if x['Debit'] > 0 else 'Payment', axis=1
            )
            book_clean['Matched'] = False
            
        except Exception as e:
            st.error(f"Error processing Ledger: {e}")
            st.stop()

        # --- Preprocessing Bank Statement ---
        try:
            df_bank.columns = df_bank.columns.str.strip()
            cols_lower = [c.lower() for c in df_bank.columns]
            
            w_idx = next((i for i, c in enumerate(cols_lower) if any(x in c for x in ['withdraw', 'debit'])), None)
            d_idx = next((i for i, c in enumerate(cols_lower) if any(x in c for x in ['deposit', 'credit'])), None)
            date_idx = next((i for i, c in enumerate(cols_lower) if 'date' in c), None)
            
            if w_idx is None or d_idx is None:
                st.error("Could not find Amount columns in Bank Statement.")
                st.write("Columns found:", df_bank.columns.tolist())
                st.stop()
            
            w_col = df_bank.columns[w_idx]
            d_col = df_bank.columns[d_idx]
            b_date_col = df_bank.columns[date_idx] if date_idx is not None else None
            
            bank_clean = df_bank.copy()
            bank_clean['Withdrawal'] = bank_clean[w_col].apply(clean_currency).fillna(0)
            bank_clean['Deposit'] = bank_clean[d_col].apply(clean_currency).fillna(0)
            
            if b_date_col:
                bank_clean['Date_Obj'] = parse_dates(bank_clean[b_date_col])
            else:
                bank_clean['Date_Obj'] = pd.NaT

            bank_clean['Match_Amount'] = bank_clean.apply(
                lambda x: x['Deposit'] if x['Deposit'] > 0 else x['Withdrawal'], axis=1
            )
            bank_clean['Type'] = bank_clean.apply(
                lambda x: 'Deposit' if x['Deposit'] > 0 else 'Withdrawal', axis=1
            )
            bank_clean['Matched'] = False
            
        except Exception as e:
            st.error(f"Error processing Bank: {e}")
            st.stop()

        # --- RECONCILIATION ENGINE ---
        st.info(f"Reconciling... (Tolerance: {date_tolerance} days)")
        
        matches = []
        
        for i, book_row in book_clean.iterrows():
            amt = book_row['Match_Amount']
            book_date = book_row['Date_Obj']
            
            if amt == 0: continue
            
            b_type = book_row['Type']
            
            if b_type == 'Receipt':
                candidates = bank_clean[
                    (bank_clean['Type'] == 'Deposit') & 
                    (np.isclose(bank_clean['Match_Amount'], amt, atol=0.01)) & 
                    (bank_clean['Matched'] == False)
                ]
            else: 
                candidates = bank_clean[
                    (bank_clean['Type'] == 'Withdrawal') & 
                    (np.isclose(bank_clean['Match_Amount'], amt, atol=0.01)) & 
                    (bank_clean['Matched'] == False)
                ]
            
            valid_candidates = candidates
            if pd.notna(book_date) and not candidates.empty:
                candidates['days_diff'] = (candidates['Date_Obj'] - book_date).abs().dt.days
                valid_candidates = candidates[candidates['days_diff'] <= date_tolerance]
                if not valid_candidates.empty:
                    valid_candidates = valid_candidates.sort_values('days_diff')

            if not valid_candidates.empty:
                bank_idx = valid_candidates.index[0]
                book_clean.at[i, 'Matched'] = True
                bank_clean.at[bank_idx, 'Matched'] = True
                
                # Narration Matching
                book_narr = str(book_row.get(next((c for c in df_book.columns if 'narration' in c.lower() or 'account' in c.lower()), 'Narration'), ''))
                bank_narr = str(bank_clean.at[bank_idx, next((c for c in df_bank.columns if 'narration' in c.lower()), 'Narration')] if next((c for c in df_bank.columns if 'narration' in c.lower()), None) else '')

                matches.append({
                    'Amount': amt,
                    'Type': b_type,
                    'Book_Date': book_row.get(date_col, ''),
                    'Bank_Date': bank_clean.at[bank_idx, b_date_col] if b_date_col else '',
                    'Book_Ref': book_narr,
                    'Bank_Ref': bank_narr
                })

        # --- Results ---
        st.success(f"Reconciliation Complete! {len(matches)} matched.")
        
        tab1, tab2, tab3 = st.tabs(["✅ Matched", "⚠️ Missing in Bank", "⚠️ Missing in Books"])
        with tab1: st.dataframe(pd.DataFrame(matches))
        with tab2: st.dataframe(book_clean[book_clean['Matched'] == False])
        with tab3: st.dataframe(bank_clean[bank_clean['Matched'] == False])
        
        buffer = io.BytesIO()
        with pd.ExcelWriter(buffer, engine='xlsxwriter') as writer:
            pd.DataFrame(matches).to_excel(writer, sheet_name='Matched', index=False)
            book_clean[book_clean['Matched'] == False].to_excel(writer, sheet_name='Missing_in_Bank', index=False)
            bank_clean[bank_clean['Matched'] == False].to_excel(writer, sheet_name='Missing_in_Books', index=False)
            
        st.download_button("📥 Download Report", buffer, "BRS_Report.xlsx")
