def list_to_float(test_list):
    """
    Convert all possible convertible elements in the list to float.
    Elements that cannot be converted to float are left unchanged.
    """
    result = []
    for item in test_list:
        try:
            result.append(float(item))
        except (ValueError, TypeError):
            result.append(item)
    return result
