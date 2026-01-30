def load_data(file, file_type):
    """Robust loader for CSV and Excel with auto-header detection."""
    df_raw = None
    used_encoding = 'utf-8'
    loader_type = 'csv' # distinct track of which method worked

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
