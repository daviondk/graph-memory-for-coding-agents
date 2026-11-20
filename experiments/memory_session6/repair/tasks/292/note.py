def find(n, m):
    """
    Return integer quotient of n divided by m.
    Handle division by zero.
    """
    if m == 0:
        raise ZeroDivisionError("division by zero")
    return n // m
