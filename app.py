import streamlit as st
import pandas as pd
import numpy as np
import io

# --- Page Configuration ---
st.set_page_config(page_title="Auto-BRS Tool", layout="wide")

st.title("🏦 Automated Bank Reconciliation System")
st.markdown("""
**Instructions:**
1. Upload your **Ledger (Book)** file.
2. Upload your **Bank Statement** file.
3. The system will auto-match transactions and provide an Excel download.
""")

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

def load_data(file, file_type):
    """Robust loader for CSV and Excel with auto-header detection."""
    df_raw = None
    used_encoding = 'utf-8'
    loader_type = 'csv' 

    # 1. Try CSV with different encodings
    encodings = ['utf-8', 'ISO-8859-1', 'cp1252']
    for enc in encodings:
        try:
            file.seek(0)
            df_raw = pd.read_csv(file, encoding=enc)
            used_encoding = enc
            loader_type = 'csv'
            break
        except (UnicodeDecodeError, pd.errors.ParserError):
            continue
    
    # 2. If CSV failed, try Excel
    if df_raw is None:
        try:
            file.seek(0)
            df_raw = pd.read_excel(file)
            loader_type = 'excel'
        except Exception:
            st.error(f"Could not read {file_type}. Please ensure it is a valid CSV or Excel file.")
            return None

    # 3. Find the Header Row (Look for 'Date')
    header_idx = -1
    if df_raw is not None:
        for i, row in df_raw.iterrows():
            row_str = row.astype(str).str.lower().tolist()
            if any("date" in s for s in row_str):
                header_idx = i
                break
    
    # 4. Reload with correct header
    try:
        file.seek(0)
        if loader_type == 'csv':
            if header_idx != -1:
                return pd.read_csv(file, header=header_idx+1, encoding=used_encoding)
            else:
                return df_raw
        else: # Excel
            if header_idx != -1:
                return pd.read_excel(file, header=header_idx+1)
            else:
                return df_raw
                
    except Exception as e:
        st.error(f"Error final processing {file_type}: {e}")
        return None

# --- Main App Logic ---

col1, col2 = st.columns(2)

with col1:
    st.subheader("1. Upload Ledger (Book)")
    ledger_file = st.file_uploader("Upload Ledger CSV/Excel", type=['csv', 'xlsx', 'xls'])

with col2:
    st.subheader("2. Upload Bank Statement")
    bank_file = st.file_uploader("Upload Bank CSV/Excel", type=['csv', 'xlsx', 'xls'])

if ledger_file and bank_file:
    st.divider()
    
    # 1. Load Data
    df_book = load_data(ledger_file, "Ledger")
    df_bank = load_data(bank_file, "Bank Statement")

    if df_book is not None and df_bank is not None:
        
        # --- Preprocessing Ledger (Book) ---
        try:
            df_book.columns = df_book.columns.str.strip()
            
            # Map Ledger Columns (Adjust if your column names differ slightly)
            # We look for "Debit(Rs.)" or just "Debit"
            debit_col = next((c for c in df_book.columns if 'Debit' in c), None)
            credit_col = next((c for c in df_book.columns if 'Credit' in c), None)
            
            if not debit_col or not credit_col:
                st.error("Could not find Debit/Credit columns in Ledger. Please check header.")
                st.stop()
                
            book_clean = df_book.copy()
            book_clean['Debit'] = book_clean[debit_col].apply(clean_currency).fillna(0)
            book_clean['Credit'] = book_clean[credit_col].apply(clean_currency).fillna(0)
            
            # Match Logic: 
            # Receipt (Debit) -> Positive
            # Payment (Credit) -> Negative (for matching logic)
            # Actually, let's keep absolute amounts for matching
            
            book_clean['Match_Amount'] = book_clean.apply(
                lambda x: x['Debit'] if x['Debit'] > 0 else x['Credit'], axis=1
            )
            book_clean['Type'] = book_clean.apply(
                lambda x: 'Receipt' if x['Debit'] > 0 else 'Payment', axis=1
            )
            book_clean['Matched'] = False
            
        except Exception as e:
            st.error(f"Error processing Ledger columns: {e}")
            st.stop()

        # --- Preprocessing Bank Statement ---
        try:
            df_bank.columns = df_bank.columns.str.strip()
            
            # Map Bank Columns (HDFC usually has "Withdrawal Amt." and "Deposit Amt.")
            w_col = next((c for c in df_bank.columns if 'Withdrawal' in c), None)
            d_col = next((c for c in df_bank.columns if 'Deposit' in c), None)
            
            if not w_col or not d_col:
                st.error("Could not find Withdrawal/Deposit columns in Bank Statement.")
                st.stop()
            
            bank_clean = df_bank.copy()
            bank_clean['Withdrawal'] = bank_clean[w_col].apply(clean_currency).fillna(0)
            bank_clean['Deposit'] = bank_clean[d_col].apply(clean_currency).fillna(0)
            
            bank_clean['Match_Amount'] = bank_clean.apply(
                lambda x: x['Deposit'] if x['Deposit'] > 0 else x['Withdrawal'], axis=1
            )
            bank_clean['Type'] = bank_clean.apply(
                lambda x: 'Deposit' if x['Deposit'] > 0 else 'Withdrawal', axis=1
            )
            bank_clean['Matched'] = False
            
        except Exception as e:
            st.error(f"Error processing Bank columns: {e}")
            st.stop()

        # --- Reconciliation Engine ---
        st.info("Reconciling transactions...")
        
        matches = []
        
        # Iterate through Book entries
        for i, book_row in book_clean.iterrows():
            amt = book_row['Match_Amount']
            if amt == 0: continue
            
            b_type = book_row['Type']
            
            # Matching Rules:
            # Book Receipt (Debit) matches Bank Deposit (Credit)
            # Book Payment (Credit) matches Bank Withdrawal (Debit)
            
            if b_type == 'Receipt':
                candidates = bank_clean[
                    (bank_clean['Type'] == 'Deposit') & 
                    (np.isclose(bank_clean['Match_Amount'], amt, atol=0.01)) & 
                    (bank_clean['Matched'] == False)
                ]
            else: # Payment
                candidates = bank_clean[
                    (bank_clean['Type'] == 'Withdrawal') & 
                    (np.isclose(bank_clean['Match_Amount'], amt, atol=0.01)) & 
                    (bank_clean['Matched'] == False)
                ]
            
            if not candidates.empty:
                # Match found - take the first one
                bank_idx = candidates.index[0]
                
                book_clean.at[i, 'Matched'] = True
                bank_clean.at[bank_idx, 'Matched'] = True
                
                # Get Narration safely
                book_narr = str(book_row.get('Short Narration', book_row.get('Account', '')))
                bank_narr = str(bank_clean.at[bank_idx, 'Narration'])
                
                match_record = {
                    'Amount': amt,
                    'Type': b_type,
                    'Book_Date': book_row['Date'],
                    'Bank_Date': bank_clean.at[bank_idx, 'Date'],
                    'Book_Ref': book_narr,
                    'Bank_Ref': bank_narr
                }
                matches.append(match_record)

        # --- Results ---
        
        unmatched_book = book_clean[book_clean['Matched'] == False]
        unmatched_bank = bank_clean[bank_clean['Matched'] == False]
        
        st.success(f"Reconciliation Complete! {len(matches)} transactions matched.")
        
        tab1, tab2, tab3 = st.tabs(["Matched", "Missing in Bank (Cheques Issued/etc)", "Missing in Books (Bank Charges/etc)"])
        
        with tab1:
            st.dataframe(pd.DataFrame(matches))
            
        with tab2:
            st.write("Entries in Ledger but NOT in Bank Statement")
            st.dataframe(unmatched_book)
            
        with tab3:
            st.write("Entries in Bank Statement but NOT in Ledger")
            st.dataframe(unmatched_bank)
            
        # --- Download Report ---
        buffer = io.BytesIO()
        with pd.ExcelWriter(buffer, engine='xlsxwriter') as writer:
            pd.DataFrame(matches).to_excel(writer, sheet_name='Matched', index=False)
            unmatched_book.to_excel(writer, sheet_name='Missing_in_Bank', index=False)
            unmatched_bank.to_excel(writer, sheet_name='Missing_in_Books', index=False)
            
        st.download_button(
            label="📥 Download Detailed Reconciliation Report",
            data=buffer,
            file_name="BRS_Report_Final.xlsx",
            mime="application/vnd.ms-excel"
        )
