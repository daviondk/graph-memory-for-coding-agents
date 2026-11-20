def is_lower(string: str) -> bool:
    """
    Return True if the string is lowercase, following standard Python str.islower() semantics.
    
    A string is considered lowercase if:
    - It contains at least one cased character (letter that can be upper or lower case)
    - All cased characters in the string are lowercase
    
    Empty strings and strings with no cased characters return False.
    """
    return string.islower()
