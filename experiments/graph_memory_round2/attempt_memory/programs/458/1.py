def rectangle_area(l, b):
    """
    Calculate the area of a rectangle given its length and breadth.
    
    Args:
        l: Length of the rectangle (should be non-negative)
        b: Breadth of the rectangle (should be non-negative)
    
    Returns:
        The area of the rectangle (l * b)
    
    Raises:
        TypeError: If l or b is not a number (int or float)
        ValueError: If l or b is negative
    """
    if not isinstance(l, (int, float)) or not isinstance(b, (int, float)):
        raise TypeError("Length and breadth must be numbers")
    if l < 0 or b < 0:
        raise ValueError("Length and breadth must be non-negative")
    return l * b
