import re

def text_match_two_three(text):
    """
    Return boolean indicating if input contains 'a' followed by exactly two or three 'b's.
    """
    pattern = r'a(b{2,3})(?!b)'
    return bool(re.search(pattern, text))
