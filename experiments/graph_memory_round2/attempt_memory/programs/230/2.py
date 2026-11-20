def replace_blank(str1, char):
    """
    Replace all whitespace characters in str1 with char.
    
    Args:
        str1: The input string.
        char: The character to replace whitespace with.
    
    Returns:
        A new string with all whitespace characters replaced by char.
    """
    if not str1:
        return str1
    result = []
    for c in str1:
        if c.isspace():
            result.append(char)
        else:
            result.append(c)
    return ''.join(result)
