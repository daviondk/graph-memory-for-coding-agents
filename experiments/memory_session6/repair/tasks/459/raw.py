import re

def remove_uppercase(str1: str) -> str:
    """
    Remove uppercase substrings from a given string using regex.
    
    This function removes all sequences of uppercase letters from the input string.
    
    Args:
        str1: The input string
        
    Returns:
        A new string with all uppercase substrings removed
    """
    return re.sub(r'[A-Z]+', '', str1)
