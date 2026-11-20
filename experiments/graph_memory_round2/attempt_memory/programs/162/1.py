def sum_series(n):
    """
    Calculate the sum of the positive integers of n+(n-2)+(n-4)... (until n-x <= 0).
    
    Args:
        n: A positive integer
        
    Returns:
        The sum of the series n + (n-2) + (n-4) + ... until the terms become <= 0
    """
    total = 0
    current = n
    while current > 0:
        total += current
        current -= 2
    return total
