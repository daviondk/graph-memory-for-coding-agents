def find_tuples(test_list, K):
    """
    Return list of tuples where every element is divisible by K.
    Handle K=0 to avoid ZeroDivisionError. Return empty list if no matches found.
    """
    if K == 0:
        return []
    
    result = []
    for item in test_list:
        if isinstance(item, tuple):
            if all(x % K == 0 for x in item):
                result.append(item)
    return result
