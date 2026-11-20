def start_withp(words):
    """
    Return a list of words from the input list that start with the letter 'p' (case-insensitive).
    """
    return [word for word in words if word.lower().startswith('p')]
