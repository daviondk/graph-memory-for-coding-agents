def highest_Power_of_2(n: int) -> int:
    """
    Return the highest power of 2 that is less than or equal to n.
    
    Args:
        n: A non-negative integer.
        
    Returns:
        The highest power of 2 <= n, or 0 if n < 1.
        
    Raises:
        ValueError: If n is negative.
    """
    if n < 0:
        raise ValueError("n must be a non-negative integer")
    if n < 1:
        return 0
    
    # Find the highest power of 2 <= n
    # Using bit_length: the highest power of 2 <= n is 2^(bit_length-1)
    return 1 << (n.bit_length() - 1)
