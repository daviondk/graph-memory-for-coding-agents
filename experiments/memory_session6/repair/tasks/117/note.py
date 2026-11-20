def list_to_float(test_list):
    """
    Convert list elements to float if possible.
    Return list of floats. Handle non-convertible elements by keeping original.
    """
    result = []
    for item in test_list:
        try:
            result.append(float(item))
        except (ValueError, TypeError):
            result.append(item)
    return result
