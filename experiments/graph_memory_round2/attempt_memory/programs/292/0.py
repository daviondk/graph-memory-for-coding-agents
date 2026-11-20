def find(n, m):
    """
    Find the quotient of two numbers (rounded down to the nearest integer).
    
    Args:
        n: The dividend (numerator)
        m: The divisor (denominator)
    
    Returns:
        The floor division result of n divided by m
    """
    if m == 0:
        raise ZeroDivisionError("division by zero")
    return n // m
