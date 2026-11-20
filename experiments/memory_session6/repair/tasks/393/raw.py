def max_length_list(input_list):
    """
    Find the list with maximum length using a lambda function.
    
    Args:
        input_list: A list of lists.
        
    Returns:
        The list with the maximum length.
    """
    return max(input_list, key=lambda x: len(x))
