def extract_string(str, l):
    """
    Extract strings of specified length from a given list of string values.
    
    Args:
        str: A list of strings (the parameter name is 'str' but it's expected to be a list)
        l: The desired length of strings to extract
        
    Returns:
        A list of strings from 'str' that have exactly length 'l'
    """
    if not isinstance(str, list):
        return []
    return [s for s in str if isinstance(s, str) and len(s) == l]
