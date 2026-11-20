def check_integer(text: str) -> bool:
    """
    Check if a string represents an integer.
    
    Args:
        text: The string to check.
        
    Returns:
        True if the string represents an integer, False otherwise.
    """
    if not isinstance(text, str):
        return False
    
    # Strip whitespace
    stripped = text.strip()
    
    if not stripped:
        return False
    
    # Check for optional sign
    start = 0
    if stripped[0] in ('+', '-'):
        start = 1
    
    # After the sign, there must be at least one digit
    if start >= len(stripped):
        return False
    
    # All remaining characters must be digits
    return stripped[start:].isdigit()
