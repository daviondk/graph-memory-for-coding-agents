def convert_list_dictionary(l1, l2, l3):
    """
    Convert three lists into a nested dictionary.
    
    Args:
        l1: List of keys for the first level
        l2: List of keys for the second level
        l3: List of values for the third level
        
    Returns:
        A nested dictionary where:
        - First level keys are from l1
        - Second level keys are from l2
        - Values are from l3
    """
    result = {}
    for i, key1 in enumerate(l1):
        result[key1] = {}
        for j, key2 in enumerate(l2):
            result[key1][key2] = l3[j] if j < len(l3) else None
    return result
