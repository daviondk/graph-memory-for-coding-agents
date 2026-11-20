def extract_rear(test_tuple):
    """
    Extract last character from each string in input tuple.
    Return tuple of characters. Handle empty strings by returning empty string for that element.
    """
    result = []
    for s in test_tuple:
        if isinstance(s, str):
            if len(s) == 0:
                result.append("")
            else:
                result.append(s[-1])
        else:
            # If not a string, handle appropriately (e.g., convert to string or skip)
            # Based on the task, we assume input is tuple of strings, but let's be safe
            result.append("")
    return tuple(result)
