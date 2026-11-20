def count_bidirectional(test_list):
    """
    Count bidirectional tuple pairs in a list of tuples.
    
    A bidirectional pair (a, b) means both (a, b) and (b, a) exist in the list.
    We count each such pair once (i.e., the number of unique unordered pairs {a, b}
    such that both (a, b) and (b, a) are present).
    
    Args:
        test_list: A list of 2-element tuples.
        
    Returns:
        The number of bidirectional pairs.
    """
    from collections import defaultdict
    
    # Count occurrences of each tuple
    count = defaultdict(int)
    for t in test_list:
        count[t] += 1
    
    # Track which pairs we've already counted to avoid double counting
    counted = set()
    result = 0
    
    for t in test_list:
        a, b = t
        if a == b:
            continue
        # Check if the reverse exists
        if (b, a) in count:
            # Use a canonical form to avoid double counting
            key = (min(a, b), max(a, b))
            if key not in counted:
                counted.add(key)
                result += 1
    
    return result
