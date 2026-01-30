def load_data(file, file_type):
    """Loads CSV and automatically finds the header row with encoding fallback."""
    # List of encodings to try
    encodings = ['utf-8', 'ISO-8859-1', 'cp1252']
    
    df_raw = None
    
    # 1. Try loading the file with different encodings
    for enc in encodings:
        try:
            file.seek(0) # Reset file pointer to the beginning
            df_raw = pd.read_csv(file, encoding=enc)
            break # If successful, stop trying
        except (UnicodeDecodeError, pd.errors.ParserError):
            continue
            
    # If standard CSV reading fails, try Excel engine (just in case user uploaded xlsx renamed as csv)
    if df_raw is None:
        try:
            file.seek(0)
            df_raw = pd.read_excel(file)
        except Exception:
            st.error(f"Could not read {file_type}. Please save your file as a standard CSV (Comma delimited) or Excel (.xlsx) file.")
            return None

    # 2. Find the Header Row
    # Look for the row containing 'Date' to treat as header
    header_idx = -1
    for i, row in df_raw.iterrows():
        # Convert row to string, lowercase it, and check for "date"
        row_str = row.astype(str).str.lower().tolist()
        if any("date" in s for s in row_str):
            header_idx = i
            break
    
    # 3. Reload with the correct header
    try:
        file.seek(0)
        # Use the successful encoding we found earlier
        used_encoding = enc if 'enc' in locals() else 'utf-8'
        
        if header_idx != -1:
            df = pd.read_csv(file, header=header_idx+1, encoding=used_encoding)
        else:
            df = df_raw # Fallback if no "Date" row found
            
        return df
    except Exception as e:
        st.error(f"Error processing {file_type}: {e}")
        return None
