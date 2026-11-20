def start_withp(words):
    """
    Return two words from a list of words starting with letter 'p'.
    
    Args:
        words: A list of words (strings).
        
    Returns:
        A list containing up to two words that start with 'p' (case-insensitive).
        If fewer than two such words exist, returns all that are found.
    """
    result = []
    for word in words:
        if word and word[0].lower() == 'p':
            result.append(word)
            if len(result) == 2:
                break
    return result
