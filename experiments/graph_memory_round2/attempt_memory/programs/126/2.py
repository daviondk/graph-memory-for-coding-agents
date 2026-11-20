def sum(a, b):
    """Return the sum of common divisors of a and b.
    
    If either a or b is zero, return 0.
    """
    if a == 0 or b == 0:
        return 0
    
    # Work with absolute values
    a_abs = abs(a)
    b_abs = abs(b)
    
    # Find the smaller of the two to iterate up to
    smaller = min(a_abs, b_abs)
    
    total = 0
    for i in range(1, smaller + 1):
        if a_abs % i == 0 and b_abs % i == 0:
            total += i
    
    return total
