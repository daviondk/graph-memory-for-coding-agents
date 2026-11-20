def smallest_num(xs):
    """
    Find the smallest number in a list.
    
    Args:
        xs: A list of numbers
        
    Returns:
        The smallest number in the list
    """
    if not xs:
        raise ValueError("Cannot find smallest number in an empty list")
    
    min_val = xs[0]
    for num in xs[1:]:
        if num < min_val:
            min_val = num
    return min_val
