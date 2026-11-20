def count_Occurrence(tup, lst):
    """
    Return dict mapping each list element to its count in tuple.
    Handle duplicates in list by summing counts.
    Return 0 for elements not in tuple.
    """
    from collections import Counter
    
    # Count occurrences in the tuple
    tuple_counts = Counter(tup)
    
    # Build result dict
    result = {}
    for item in lst:
        if item in result:
            result[item] += tuple_counts.get(item, 0)
        else:
            result[item] = tuple_counts.get(item, 0)
    
    return result
