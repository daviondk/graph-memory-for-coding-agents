def even_Power_Sum(n):
    """
    Find the sum of fifth power of first n even natural numbers.
    
    Args:
        n: Number of first even natural numbers to consider
        
    Returns:
        Sum of fifth powers of first n even natural numbers
    """
    total = 0
    for i in range(1, n + 1):
        even_num = 2 * i
        total += even_num ** 5
    return total
