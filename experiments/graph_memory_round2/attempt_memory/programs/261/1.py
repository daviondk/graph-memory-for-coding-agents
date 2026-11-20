def division_elements(test_tup1, test_tup2):
    """
    Perform element-wise division of two tuples.
    
    Args:
        test_tup1: First tuple (dividend)
        test_tup2: Second tuple (divisor)
    
    Returns:
        A tuple containing the element-wise division results.
        If a division by zero occurs, returns None for that element.
        If tuples have different lengths, uses the shorter length.
    """
    if not isinstance(test_tup1, tuple) or not isinstance(test_tup2, tuple):
        raise TypeError("Both inputs must be tuples")
    
    min_len = min(len(test_tup1), len(test_tup2))
    result = []
    
    for i in range(min_len):
        a = test_tup1[i]
        b = test_tup2[i]
        
        # Check if both are numeric
        if not isinstance(a, (int, float)) or not isinstance(b, (int, float)):
            raise TypeError(f"Elements at index {i} must be numeric")
        
        if b == 0:
            result.append(None)
        else:
            result.append(a / b)
    
    return tuple(result)
