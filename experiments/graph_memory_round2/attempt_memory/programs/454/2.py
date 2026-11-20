def text_match_wordz(text):
    """
    Return boolean if any word in text contains 'z'.
    Handle empty text, non-string input, and case sensitivity.
    """
    if not isinstance(text, str):
        return False
    if not text:
        return False
    # Split into words (by whitespace)
    words = text.split()
    for word in words:
        if 'z' in word.lower():
            return True
    return False
