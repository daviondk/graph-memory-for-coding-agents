def merge_sorted_list(num1, num2, num3):
    """
    Merge three lists into a single sorted list.
    
    Args:
        num1: First list of numbers
        num2: Second list of numbers
        num3: Third list of numbers
    
    Returns:
        A single sorted list containing all elements from the three input lists.
    """
    # Handle edge cases: None inputs or empty lists
    lists = [num1, num2, num3]
    
    # Filter out None values and flatten
    all_elements = []
    for lst in lists:
        if lst is not None:
            all_elements.extend(lst)
    
    # Sort the combined list
    return sorted(all_elements)
