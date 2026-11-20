def divisor(n):
    """
    Return the number of positive divisors of the integer n.
    
    Args:
        n: A positive integer.
        
    Returns:
        The number of positive divisors of n.
        
    Raises:
        ValueError: If n is not a positive integer.
    """
    if not isinstance(n, int) or n <= 0:
        raise ValueError("Input must be a positive integer.")
    
    if n == 1:
        return 1
    
    count = 0
    i = 1
    while i * i <= n:
        if n % i == 0:
            if i * i == n:
                count += 1
            else:
                count += 2
        i += 1
    
    return count
