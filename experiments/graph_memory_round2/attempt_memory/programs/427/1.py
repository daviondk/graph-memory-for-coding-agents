import re

def change_date_format(dt: str) -> str:
    """
    Convert a date from yyyy-mm-dd format to dd-mm-yyyy format using regex.
    
    Args:
        dt: A string in yyyy-mm-dd format
        
    Returns:
        A string in dd-mm-yyyy format
    """
    match = re.match(r'^(\d{4})-(\d{2})-(\d{2})$', dt)
    if not match:
        raise ValueError(f"Invalid date format: {dt}. Expected yyyy-mm-dd.")
    
    year, month, day = match.groups()
    return f"{day}-{month}-{year}"
