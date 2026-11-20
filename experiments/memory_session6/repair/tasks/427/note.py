import re

def change_date_format(dt: str) -> str:
    """
    Convert a date string from yyyy-mm-dd format to dd-mm-yyyy format using regex.
    
    Args:
        dt: A date string in yyyy-mm-dd format.
        
    Returns:
        A date string in dd-mm-yyyy format.
    """
    match = re.match(r'^(\d{4})-(\d{2})-(\d{2})$', dt)
    if not match:
        raise ValueError(f"Invalid date format: {dt}")
    
    year, month, day = match.groups()
    return f"{day}-{month}-{year}"
