def tetrahedral_number(n):
    """
    Return the nth tetrahedral number.
    
    The nth tetrahedral number is the sum of the first n triangular numbers,
    which can be computed as n*(n+1)*(n+2)//6.
    
    Edge cases:
    - If n is 0, return 0.
    - If n is negative, raise a ValueError.
    """
    if n < 0:
        raise ValueError("n must be a non-negative integer")
    if n == 0:
        return 0
    return n * (n + 1) * (n + 2) // 6
