def last_Digit(n):
    """
    Find the last digit of a given number.
    
    Args:
        n: An integer (positive or negative)
        
    Returns:
        The last digit of the number (0-9)
    """
    return abs(n) % 10
