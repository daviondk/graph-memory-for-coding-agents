def find_substring(str1, sub_str):
    """
    Check if sub_str is a substring of any string in the list str1.
    
    Args:
        str1: A list of strings.
        sub_str: The substring to search for.
    
    Returns:
        True if sub_str is found as a substring in any string in str1, False otherwise.
    """
    return any(sub_str in s for s in str1)
