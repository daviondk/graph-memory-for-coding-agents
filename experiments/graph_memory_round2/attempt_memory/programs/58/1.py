def opposite_Signs(x, y):
    """
    Check whether the given two integers have opposite signs.
    
    Args:
        x: First integer
        y: Second integer
    
    Returns:
        True if x and y have opposite signs, False otherwise.
        Note: Zero is neither positive nor negative, so if either
        x or y is zero, the function returns False.
    """
    if x == 0 or y == 0:
        return False
    return (x > 0 and y < 0) or (x < 0 and y > 0)
