def max_aggregate(stdata):
    """
    Compute max aggregate from list of tuples.
    
    Each tuple is expected to contain at least two elements:
    - First element: a key (hashable)
    - Second element: a numeric value
    
    The function aggregates values by key (summing them) and returns
    the key with the maximum aggregate value.
    
    If the list is empty, returns None.
    """
    if not stdata:
        return None
    
    # Aggregate values by key
    aggregates = {}
    for item in stdata:
        if not isinstance(item, tuple) or len(item) < 2:
            continue
        key, value = item[0], item[1]
        if not isinstance(value, (int, float)):
            continue
        if key in aggregates:
            aggregates[key] += value
        else:
            aggregates[key] = value
    
    if not aggregates:
        return None
    
    # Find the key with the maximum aggregate value
    max_key = max(aggregates, key=lambda k: aggregates[k])
    return max_key
