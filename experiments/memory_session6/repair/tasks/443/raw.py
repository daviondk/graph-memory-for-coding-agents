def largest_neg(list1):
    """
    Find the largest negative number from the given list.
    
    Args:
        list1: A list of numbers.
        
    Returns:
        The largest negative number in the list, or None if no negative numbers exist.
    """
    negatives = [x for x in list1 if x < 0]
    if not negatives:
        return None
    return max(negatives)
