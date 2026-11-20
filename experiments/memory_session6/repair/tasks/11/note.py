def remove_Occ(s, ch):
    """
    Remove first and last occurrence of ch from s.
    If ch appears only once, remove it.
    If ch does not appear, return s unchanged.
    """
    if not s or not ch:
        return s
    
    # Find first occurrence
    first_idx = s.find(ch)
    if first_idx == -1:
        return s
    
    # Find last occurrence
    last_idx = s.rfind(ch)
    
    if first_idx == last_idx:
        # Only one occurrence, remove it
        return s[:first_idx] + s[first_idx + len(ch):]
    else:
        # Remove first and last occurrences
        # Remove last first (since it's at a higher index)
        result = s[:last_idx] + s[last_idx + len(ch):]
        # Now remove first occurrence from the modified string
        # But we need to be careful: the first occurrence index is still valid
        # since we removed something after it
        result = result[:first_idx] + result[first_idx + len(ch):]
        return result
