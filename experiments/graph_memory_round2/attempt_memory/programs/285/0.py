import re

def text_match_two_three(text):
    """
    Check whether a string contains the 'a' character followed by two or three 'b' characters.
    
    Args:
        text: The input string to check.
        
    Returns:
        True if the string contains 'a' followed by exactly two or three 'b's, False otherwise.
    """
    pattern = r'a(b{2,3})'
    return bool(re.search(pattern, text))
