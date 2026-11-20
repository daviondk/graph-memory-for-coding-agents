def count_bidirectional(test_list):
    """
    Count pairs (a,b) where both (a,b) and (b,a) exist in test_list.
    Return integer count. Handle empty lists and single elements returning zero.
    """
    if not test_list:
        return 0
    
    # Convert to a set of tuples for O(1) lookup
    pair_set = set(test_list)
    
    count = 0
    seen = set()
    
    for pair in test_list:
        a, b = pair
        reversed_pair = (b, a)
        if reversed_pair in pair_set:
            # To avoid double counting, only count each bidirectional pair once
            # We can use a canonical form: sort the pair
            key = tuple(sorted([a, b]))
            if key not in seen:
                seen.add(key)
                count += 1
    
    return count
