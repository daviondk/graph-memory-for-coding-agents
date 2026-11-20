import re


def text_match_wordz(text):
    """
    Match a word containing 'z' in the given text.
    
    Args:
        text: A string to search for a word containing 'z'.
        
    Returns:
        A match object if a word containing 'z' is found, otherwise None.
    """
    pattern = r'\b\w*z\w*\b'
    return re.search(pattern, text)
