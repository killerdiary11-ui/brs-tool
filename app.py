import streamlit as st
import pandas as pd
import numpy as np

# --- Page Configuration ---
st.set_page_config(page_title="Auto-BRS Tool", layout="wide")

st.title("🏦 Automated Bank Reconciliation System")
st.markdown("""
Upload your **Ledger (Book)** and **Bank Statement** below. 
The system will auto-match transactions based on Amount and Direction (Debit/Credit).
""")

# --- Helper Functions ---

def clean_currency(x):
    """Removes commas and converts to float."""
    if isinstance(x, str):
        # Remove commas and handle any brackets or negative signs if present
        clean_str = x.replace(',', '').replace(' Dr', '').replace(' Cr', '').strip()
        try:
            return float(clean_str) if clean_str else 0.0
        except ValueError:
            return 0.0
    return x

def load_data(file, file_type):
    """Loads CSV and automatically finds the header row."""
    # Read first few lines to find the header
    try:
        df_raw = pd.read_csv(file)
        # Look for the row containing 'Date' to treat as header
        header_idx = -1
        for i, row in df_raw.iterrows():
            row_str = row.astype(str).str.lower().tolist()
            if any("date" in s for s in row_str):
                header_idx = i
                break
        
        if header_idx != -1:
            # Reload with correct header
            file.seek(0)
            df = pd.read_csv(file, header=header_idx+1)
        else:
            df = df_raw # Fallback
            
        return df
    except Exception as e:
        st.error(f"Error loading {file_type}: {e}")
        return None

# --- Main App Logic ---

col1, col2 = st.columns(2)

with col1:
    st.subheader("1. Upload Ledger (Book)")
    ledger_file = st.file_uploader("Upload Ledger CSV", type=['csv', 'xlsx'])

with col2:
    st.subheader("2. Upload Bank Statement")
    bank_file = st.file_uploader("Upload Bank CSV", type=['csv', 'xlsx'])

if ledger_file and bank_file:
    st.divider()
    
    # 1. Load Data
    df_book = load_data(ledger_file, "Ledger")
    df_bank = load_data(bank_file, "Bank Statement")

    if df_book is not None and df_bank is not None:
        
        # --- Preprocessing Ledger (Book) ---
        # Standardizing column names for Book
        # Book structure: Debit(Rs.) = Receipt (Money In), Credit(Rs.) = Payment (Money Out)
        # We need to map columns based on your file structure
        try:
            # Clean column names
            df_book.columns = df_book.columns.str.strip()
            
            # Extract relevant columns
            book_clean = df_book[['Date', 'Vch/Bill No', 'Account', 'Debit(Rs.)', 'Credit(Rs.)', 'Short Narration']].copy()
            
            # Clean Amounts
            book_clean['Debit'] = book_clean['Debit(Rs.)'].apply(clean_currency).fillna(0)
            book_clean['Credit'] = book_clean['Credit(Rs.)'].apply(clean_currency).fillna(0)
            
            # Create a 'Net Amount' column for matching logic
            # For Book: Debit is Positive (In), Credit is Negative (Out) - relative to Bank Balance? 
            # Actually, let's stick to standard BRS matching:
            # Book Debit matches Bank Credit (Deposit)
            # Book Credit matches Bank Debit (Withdrawal)
            
            book_clean['Match_Amount'] = book_clean.apply(
                lambda x: x['Debit'] if x['Debit'] > 0 else x['Credit'], axis=1
            )
            book_clean['Type'] = book_clean.apply(
                lambda x: 'Receipt' if x['Debit'] > 0 else 'Payment', axis=1
            )
            # Add unique ID for tracking
            book_clean['ID'] = range(len(book_clean))
            book_clean['Matched'] = False
            
        except KeyError as e:
            st.error(f"Column missing in Ledger: {e}. Please ensure CSV format matches the sample.")
            st.stop()

        # --- Preprocessing Bank Statement ---
        try:
            # Clean column names
            df_bank.columns = df_bank.columns.str.strip()
            
            # Extract relevant columns (based on HDFC format provided)
            # HDFC format: 'Withdrawal Amt.', 'Deposit Amt.'
            bank_clean = df_bank[['Date', 'Narration', 'Withdrawal Amt.', 'Deposit Amt.']].copy()
            
            # Clean Amounts
            bank_clean['Withdrawal'] = bank_clean['Withdrawal Amt.'].apply(clean_currency).fillna(0)
            bank_clean['Deposit'] = bank_clean['Deposit Amt.'].apply(clean_currency).fillna(0)
            
            bank_clean['Match_Amount'] = bank_clean.apply(
                lambda x: x['Deposit'] if x['Deposit'] > 0 else x['Withdrawal'], axis=1
            )
            bank_clean['Type'] = bank_clean.apply(
                lambda x: 'Deposit' if x['Deposit'] > 0 else 'Withdrawal', axis=1
            )
            # Add unique ID for tracking
            bank_clean['ID'] = range(len(bank_clean))
            bank_clean['Matched'] = False
            
        except KeyError as e:
            st.error(f"Column missing in Bank Statement: {e}")
            st.stop()

        # --- Reconciliation Engine ---
        
        st.write("Running Reconciliation...")
        
        # We perform matching on Amount and Direction
        # Book Receipt (Debit) <-> Bank Deposit (Credit)
        # Book Payment (Credit) <-> Bank Withdrawal (Debit)
        
        matches = []
        
        # Iterate through Book entries
        for i, book_row in book_clean.iterrows():
            amt = book_row['Match_Amount']
            if amt == 0: continue
            
            b_type = book_row['Type']
            
            # Find candidate in Bank
            if b_type == 'Receipt':
                # Look for Bank Deposit of same amount that hasn't been matched
                candidates = bank_clean[
                    (bank_clean['Type'] == 'Deposit') & 
                    (bank_clean['Match_Amount'] == amt) & 
                    (bank_clean['Matched'] == False)
                ]
            else: # Payment
                # Look for Bank Withdrawal of same amount
                candidates = bank_clean[
                    (bank_clean['Type'] == 'Withdrawal') & 
                    (bank_clean['Match_Amount'] == amt) & 
                    (bank_clean['Matched'] == False)
                ]
            
            if not candidates.empty:
                # MATCH FOUND!
                # We pick the first one (FIFO logic roughly applies if sorted by date, but exact match is priority)
                bank_idx = candidates.index[0]
                
                # Mark both as matched
                book_clean.at[i, 'Matched'] = True
                bank_clean.at[bank_idx, 'Matched'] = True
                
                match_record = {
                    'Amount': amt,
                    'Book_Date': book_row['Date'],
                    'Bank_Date': bank_clean.at[bank_idx, 'Date'],
                    'Book_Narration': book_row['Account'] if pd.notna(book_row['Account']) else book_row['Short Narration'],
                    'Bank_Narration': bank_clean.at[bank_idx, 'Narration']
                }
                matches.append(match_record)

        # --- Results ---
        
        # 1. Unreconciled Book Items (Missing in Bank)
        unmatched_book = book_clean[book_clean['Matched'] == False].copy()
        
        # 2. Unreconciled Bank Items (Missing in Books)
        unmatched_bank = bank_clean[bank_clean['Matched'] == False].copy()
        
        # Display Stats
        st.metric("Total Matches Found", len(matches))
        
        tab1, tab2, tab3 = st.tabs(["✅ Matched", "⚠️ Unmatched in Book", "⚠️ Unmatched in Bank"])
        
        with tab1:
            st.dataframe(pd.DataFrame(matches))
            
        with tab2:
            st.write("**Transactions in Ledger but NOT in Bank** (Cheques issued but not presented, etc.)")
            st.dataframe(unmatched_book[['Date', 'Account', 'Debit', 'Credit', 'Short Narration']])
            
        with tab3:
            st.write("**Transactions in Bank but NOT in Ledger** (Bank Charges, Direct Deposits, etc.)")
            st.dataframe(unmatched_bank[['Date', 'Narration', 'Withdrawal', 'Deposit']])
            
        # --- Download Report ---
        
        # Create a combined Excel file for download
        output_file = "Reconciliation_Report.xlsx"
        
        # Buffer to save excel in memory
        import io
        buffer = io.BytesIO()
        
        with pd.ExcelWriter(buffer, engine='xlsxwriter') as writer:
            pd.DataFrame(matches).to_excel(writer, sheet_name='Matched', index=False)
            unmatched_book[['Date', 'Account', 'Debit', 'Credit', 'Short Narration']].to_excel(writer, sheet_name='Missing_in_Bank', index=False)
            unmatched_bank[['Date', 'Narration', 'Withdrawal', 'Deposit']].to_excel(writer, sheet_name='Missing_in_Books', index=False)
            
        st.download_button(
            label="Download Full BRS Report (Excel)",
            data=buffer,
            file_name="BRS_Report.xlsx",
            mime="application/vnd.ms-excel"
        )
