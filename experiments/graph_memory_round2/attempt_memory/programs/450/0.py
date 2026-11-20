def extract_string(str, l):
    """
    Extract strings of specified length from a list of strings.
    
    Args:
        str: A list of strings.
        l: The desired length of strings to extract.
    
    Returns:
        A list of strings from 'str' that have length equal to 'l'.
    """
    return [s for s in str if len(s) == l]
