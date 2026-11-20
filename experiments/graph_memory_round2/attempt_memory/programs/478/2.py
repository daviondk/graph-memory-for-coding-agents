def remove_lowercase(str1: str) -> str:
    """
    Remove all lowercase letters from the input string.
    
    Args:
        str1: The input string.
        
    Returns:
        A string containing only non-lowercase characters.
    """
    return ''.join(char for char in str1 if not char.islower())
