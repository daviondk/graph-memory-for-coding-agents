def centered_hexagonal_number(n):
    """
    Find the nth centered hexagonal number.
    
    The centered hexagonal numbers are given by the formula:
    H_n = 3n(n-1) + 1
    
    where n is a positive integer (n >= 1).
    
    Args:
        n: A positive integer representing the index (1-based) of the centered hexagonal number.
        
    Returns:
        The nth centered hexagonal number.
    """
    if n < 1:
        raise ValueError("n must be a positive integer")
    return 3 * n * (n - 1) + 1
