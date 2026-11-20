def median_trapezium(base1, base2, height):
    """
    Find the median (midline) length of a trapezium.
    
    The median (or midline) of a trapezium is the line segment connecting
    the midpoints of the non-parallel sides. Its length is the average of
    the two parallel bases.
    
    Parameters:
    base1 (float): Length of the first parallel side
    base2 (float): Length of the second parallel side
    height (float): Height of the trapezium (not used in median calculation)
    
    Returns:
    float: The length of the median (midline) of the trapezium
    """
    if base1 < 0 or base2 < 0:
        raise ValueError("Base lengths must be non-negative")
    if height < 0:
        raise ValueError("Height must be non-negative")
    
    return (base1 + base2) / 2.0
