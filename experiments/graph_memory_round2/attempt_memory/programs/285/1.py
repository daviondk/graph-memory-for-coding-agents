import re

def text_match_two_three(text):
    """
    Match a string that has an 'a' followed by two to three 'b's.
    
    Args:
        text: The input string to match.
        
    Returns:
        True if the string matches the pattern, False otherwise.
    """
    pattern = r'^a{1}b{2,3}$'
    return bool(re.match(pattern, text))
