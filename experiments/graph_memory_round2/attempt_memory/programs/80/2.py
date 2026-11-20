def tetrahedral_number(n):
    """
    Find the nth tetrahedral number.
    
    The nth tetrahedral number is the sum of the first n triangular numbers.
    Formula: n(n+1)(n+2)/6
    
    Args:
        n: A positive integer representing the position in the sequence
        
    Returns:
        The nth tetrahedral number
    """
    if n < 1:
        raise ValueError("n must be a positive integer")
    return n * (n + 1) * (n + 2) // 6
