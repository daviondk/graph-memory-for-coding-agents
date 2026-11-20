def get_Char(strr):
    """
    Find the character made by adding the ASCII value of all the characters of the given string modulo 26.
    
    Args:
        strr: A string input
        
    Returns:
        A single character corresponding to the sum of ASCII values modulo 26, mapped to 'a'-'z'
    """
    total = sum(ord(c) for c in strr)
    # Map the result modulo 26 to a character from 'a' to 'z'
    char = chr(ord('a') + (total % 26))
    return char
