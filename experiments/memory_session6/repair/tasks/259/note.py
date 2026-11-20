def maximize_elements(test_tup1, test_tup2):
    """
    Return a tuple with element-wise maximums of two tuples.
    If lengths differ, pad the shorter tuple with zeros.
    """
    len1 = len(test_tup1)
    len2 = len(test_tup2)
    max_len = max(len1, len2)
    
    # Pad shorter tuple with zeros
    if len1 < max_len:
        test_tup1 = test_tup1 + (0,) * (max_len - len1)
    if len2 < max_len:
        test_tup2 = test_tup2 + (0,) * (max_len - len2)
    
    return tuple(max(a, b) for a, b in zip(test_tup1, test_tup2))
