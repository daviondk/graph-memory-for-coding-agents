def add_lists(test_list, test_tup):
    """
    Append the given list to the given tuples.
    
    Args:
        test_list: A list to be appended to each tuple in test_tup.
        test_tup: A tuple of tuples (or a single tuple) to which test_list is appended.
        
    Returns:
        A tuple of tuples where each original tuple has test_list appended to it.
    """
    # If test_tup is a single tuple (not a tuple of tuples), wrap it in a tuple
    if isinstance(test_tup, tuple) and all(isinstance(item, tuple) for item in test_tup):
        # test_tup is a tuple of tuples
        return tuple(tuple(t) + tuple(test_list) for t in test_tup)
    elif isinstance(test_tup, tuple):
        # test_tup is a single tuple
        return (tuple(test_tup) + tuple(test_list),)
    else:
        # If test_tup is not a tuple, treat it as a single item
        return (tuple(test_tup) + tuple(test_list),) if not isinstance(test_tup, tuple) else (tuple(test_tup) + tuple(test_list),)
