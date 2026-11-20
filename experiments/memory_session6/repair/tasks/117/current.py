def list_to_float(test_list):
    """
    Convert all possible convertible elements in a list of lists to floats.
    
    Args:
        test_list: A list of lists containing elements that may be convertible to floats.
        
    Returns:
        A new list of lists where all convertible elements have been converted to floats.
        Elements that cannot be converted to floats are left unchanged.
    """
    result = []
    for sublist in test_list:
        new_sublist = []
        for element in sublist:
            try:
                new_sublist.append(float(element))
            except (ValueError, TypeError):
                new_sublist.append(element)
        result.append(new_sublist)
    return result
