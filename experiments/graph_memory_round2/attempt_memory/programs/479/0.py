def first_Digit(n):
    """
    Find the first digit of a given number.
    
    Args:
        n: A number (int or float)
        
    Returns:
        The first digit of the number as an integer.
    """
    # Handle negative numbers by taking absolute value
    n = abs(n)
    
    # Convert to string and remove decimal point if present
    s = str(n)
    if '.' in s:
        s = s.replace('.', '')
    
    # Return the first character as an integer
    return int(s[0])
