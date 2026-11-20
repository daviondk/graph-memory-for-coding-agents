def median_trapezium(base1, base2, height):
    """
    Calculate the median (midline) of a trapezium.
    
    The median of a trapezium is the line segment connecting the midpoints
    of the non-parallel sides. Its length is the average of the lengths of
    the two parallel bases.
    
    Args:
        base1 (float): Length of the first base (parallel side)
        base2 (float): Length of the second base (parallel side)
        height (float): Height of the trapezium (not used in median calculation)
    
    Returns:
        float: The length of the median
    """
    return (base1 + base2) / 2.0
