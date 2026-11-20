def highest_Power_of_2(n):
    """
    Find the highest power of 2 that is less than or equal to n.
    
    Args:
        n: A positive integer
        
    Returns:
        The highest power of 2 less than or equal to n
    """
    if n <= 0:
        raise ValueError("n must be a positive integer")
    
    power = 1
    while power * 2 <= n:
        power *= 2
    return power
