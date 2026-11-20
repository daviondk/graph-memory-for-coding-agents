def remove_Occ(s, ch):
    """
    Remove the first and last occurrence of a given character from the string.
    
    Args:
        s: Input string
        ch: Character to remove (first and last occurrence)
    
    Returns:
        String with the first and last occurrence of ch removed
    """
    if not s or not ch:
        return s
    
    # Find the first occurrence
    first_idx = s.find(ch)
    if first_idx == -1:
        return s
    
    # Find the last occurrence
    last_idx = s.rfind(ch)
    
    # If first and last are the same, remove only that one occurrence
    if first_idx == last_idx:
        return s[:first_idx] + s[first_idx + 1:]
    else:
        # Remove both first and last occurrences
        return s[:first_idx] + s[first_idx + 1:last_idx] + s[last_idx + 1:]
