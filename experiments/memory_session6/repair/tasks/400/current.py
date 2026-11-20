def extract_freq(test_list):
    """
    Extract the number of unique tuples in the given list.
    
    Args:
        test_list: A list containing tuples (and possibly other elements).
        
    Returns:
        The count of unique tuples in the list.
    """
    # Filter only tuples from the list
    tuples_in_list = [item for item in test_list if isinstance(item, tuple)]
    
    # Convert to set to get unique tuples
    unique_tuples = set(tuples_in_list)
    
    # Return the count of unique tuples
    return len(unique_tuples)
