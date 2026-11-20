def count_Occurrence(tup, lst):
    """
    Count the occurrence of all elements of list in a tuple.
    
    Args:
        tup: A tuple of elements.
        lst: A list of elements to count in the tuple.
    
    Returns:
        A dictionary where keys are elements from lst and values are their counts in tup.
    """
    result = {}
    for item in lst:
        result[item] = tup.count(item)
    return result
