def change_date_format(dt: str) -> str:
    """
    Convert a date string from yyyy-mm-dd format to dd-mm-yyyy format.
    
    Args:
        dt: A date string in yyyy-mm-dd format.
        
    Returns:
        A date string in dd-mm-yyyy format.
    """
    year, month, day = dt.split('-')
    return f"{day}-{month}-{year}"
