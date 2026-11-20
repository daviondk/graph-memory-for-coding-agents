def convert_list_dictionary(l1, l2, l3):
    """
    Convert three lists into a nested dictionary.
    
    The structure is:
    - Keys from l1
    - Sub-keys from l2
    - Values from l3
    
    If the lists have different lengths, the shortest list determines the depth.
    Each element in l1 maps to a dictionary where each element in l2 maps to the
    corresponding element in l3.
    
    For example:
    l1 = ['a', 'b']
    l2 = ['x', 'y']
    l3 = [1, 2]
    
    Result:
    {
        'a': {'x': 1, 'y': 2},
        'b': {'x': 1, 'y': 2}
    }
    
    If lists have different lengths, we zip them together (shortest wins).
    """
    result = {}
    for key in l1:
        result[key] = {}
        for subkey, value in zip(l2, l3):
            result[key][subkey] = value
    return result
