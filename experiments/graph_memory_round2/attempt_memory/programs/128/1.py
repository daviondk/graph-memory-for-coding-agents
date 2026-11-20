def long_words(n, str):
    """
    Find words that are longer than n characters from a given string.
    
    Args:
        n: An integer representing the minimum length threshold.
        str: A string containing words separated by whitespace.
        
    Returns:
        A list of words that are longer than n characters.
    """
    if not str:
        return []
    
    words = str.split()
    return [word for word in words if len(word) > n]
