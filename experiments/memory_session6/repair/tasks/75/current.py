def find_tuples(test_list, K):
    """
    Find tuples which have all elements divisible by K from the given list of tuples.
    
    Args:
        test_list: A list of tuples.
        K: An integer divisor.
    
    Returns:
        A list of tuples where all elements are divisible by K.
    """
    return [t for t in test_list if all(x % K == 0 for x in t)]
