def find(n, m):
    """
    Find the quotient of two numbers n and m.
    
    Args:
        n: The dividend (numerator)
        m: The divisor (denominator)
    
    Returns:
        The quotient of n divided by m.
        Returns None if m is 0 to avoid division by zero.
    """
    if m == 0:
        return None
    return n / m
