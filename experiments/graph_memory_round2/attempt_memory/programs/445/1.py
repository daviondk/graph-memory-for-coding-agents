def index_multiplication(test_tup1, test_tup2):
    """
    Perform index-wise multiplication of two tuples.
    
    Args:
        test_tup1: First tuple of numbers
        test_tup2: Second tuple of numbers
    
    Returns:
        A tuple where each element is the product of corresponding elements
        from the input tuples. If tuples have different lengths, the result
        has the length of the shorter tuple.
    """
    min_len = min(len(test_tup1), len(test_tup2))
    return tuple(test_tup1[i] * test_tup2[i] for i in range(min_len))
