def remove_lowercase(str1: str) -> str:
    """
    Remove lowercase substrings from a given string.
    
    This function removes all lowercase letters from the input string,
    keeping only uppercase letters and non-alphabetic characters.
    
    Args:
        str1: The input string.
        
    Returns:
        A string with all lowercase letters removed.
    """
    return ''.join(char for char in str1 if not char.islower())
