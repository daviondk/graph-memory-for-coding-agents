def check_integer(text: str) -> bool:
    """
    Return True if the input string is a valid integer, False otherwise.
    
    A valid integer may have:
    - Leading/trailing whitespace
    - An optional sign (+ or -)
    - One or more digits
    
    No other characters are allowed.
    """
    if not isinstance(text, str):
        return False
    
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
