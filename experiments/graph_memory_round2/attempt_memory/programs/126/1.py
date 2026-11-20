def sum(a: int, b: int) -> int:
    """
    Find the sum of common divisors of two given numbers.
    
    Args:
        a: First integer
        b: Second integer
    
    Returns:
        Sum of all common divisors of a and b
    """
    # Handle edge cases
    if a == 0 and b == 0:
        return 0
    if a == 0:
        return abs(b)
    if b == 0:
        return abs(a)
    
    a = abs(a)
    b = abs(b)
    
    # Find the smaller number to iterate up to
    smaller = min(a, b)
    
    total = 0
    for i in range(1, smaller + 1):
        if a % i == 0 and b % i == 0:
            total += i
    
    return total
