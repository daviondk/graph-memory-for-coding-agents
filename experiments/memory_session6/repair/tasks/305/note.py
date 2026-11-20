def start_withp(words):
    """
    Return first two words starting with 'p'.
    Handle lists with fewer than two matches by returning available matches or empty list.
    """
    result = []
    for word in words:
        if word.startswith('p'):
            result.append(word)
            if len(result) == 2:
                break
    return result
