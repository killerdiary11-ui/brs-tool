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

    # 3. Find the Header Row (Look for specific columns)
    header_idx = -1
    if df_raw is not None:
        for i, row in df_raw.iterrows():
            row_str = row.astype(str).str.lower().tolist()
            
            # CRITICAL FIX: Ledger usually has "Vch/Bill" or "Account", Bank has "Narration"
            # We use loose matching to capture both styles
            is_bank_header = any("narration" in s for s in row_str) and any("date" in s for s in row_str)
            is_book_header = any("vch" in s for s in row_str) or (any("account" in s for s in row_str) and any("debit" in s for s in row_str))
            
            if is_bank_header or is_book_header:
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
            
            # Case-insensitive column search
            cols_lower = [c.lower() for c in df_book.columns]
            
            # Find Debit Column
            debit_idx = next((i for i, c in enumerate(cols_lower) if 'debit' in c), None)
            # Find Credit Column
            credit_idx = next((i for i, c in enumerate(cols_lower) if 'credit' in c), None)
            
            if debit_idx is None or credit_idx is None:
                st.error("Could not find Debit/Credit columns in Ledger. Please ensure header row is correct.")
                st.write("Columns found:", df_book.columns.tolist())
                st.stop()
            
            # Get actual column names
            debit_col = df_book.columns[debit_idx]
            credit_col = df_book.columns[credit_idx]
                
            book_clean = df_book.copy()
            book_clean['Debit'] = book_clean[debit_col].apply(clean_currency).fillna(0)
            book_clean['Credit'] = book_clean[credit_col].apply(clean_currency).fillna(0)
            
            # Standardize Dates (Optional but recommended)
            # book_clean['Date'] = pd.to_datetime(book_clean['Date'], errors='coerce')

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
            cols_lower = [c.lower() for c in df_bank.columns]
            
            # Find Withdrawal Column
            w_idx = next((i for i, c in enumerate(cols_lower) if 'withdrawal' in c), None)
            # Find Deposit Column
            d_idx = next((i for i, c in enumerate(cols_lower) if 'deposit' in c), None)
            
            if w_idx is None or d_idx is None:
                st.error("Could not find Withdrawal/Deposit columns in Bank Statement.")
                st.write("Columns found:", df_bank.columns.tolist())
                st.stop()
            
            w_col = df_bank.columns[w_idx]
            d_col = df_bank.columns[d_idx]
            
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
                # Try to find common narration columns
                book_narr_col = next((c for c in df_book.columns if 'narration' in c.lower() or 'account' in c.lower()), 'Narration')
                bank_narr_col = next((c for c in df_bank.columns if 'narration' in c.lower()), 'Narration')
                
                book_narr = str(book_row.get(book_narr_col, ''))
                bank_narr = str(bank_clean.at[bank_idx, bank_narr_col]) if bank_narr_col in bank_clean.columns else ''
                
                match_record = {
                    'Amount': amt,
                    'Type': b_type,
                    'Book_Date': book_row.get('Date', ''),
                    'Bank_Date': bank_clean.at[bank_idx, 'Date'] if 'Date' in bank_clean.columns else '',
                    'Book_Ref': book_narr,
                    'Bank_Ref': bank_narr
                }
                matches.append(match_record)

        # --- Results ---
        
        unmatched_book = book_clean[book_clean['Matched'] == False]
        unmatched_bank = bank_clean[bank_clean['Matched'] == False]
        
        st.success(f"Reconciliation Complete! {len(matches)} transactions matched.")
        
        tab1, tab2, tab3 = st.tabs(["Matched", "Missing in Bank", "Missing in Books"])
        
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
