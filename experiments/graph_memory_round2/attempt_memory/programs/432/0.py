def median_trapezium(base1, base2, height):
    """
    Find the median length of a trapezium (trapezoid).
    
    The median (or midline) of a trapezium is the segment connecting the midpoints
    of the non-parallel sides. Its length is the average of the two bases.
    
    Parameters:
    base1 (float): Length of the first base
    base2 (float): Length of the second base
    height (float): Height of the trapezium (not needed for median calculation)
    
    Returns:
    float: The median length of the trapezium
    """
    return (base1 + base2) / 2
