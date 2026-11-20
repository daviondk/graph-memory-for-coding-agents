def first_non_repeating_character(str1):
    if not str1:
        return None
    count = {}
    for ch in str1:
        count[ch] = count.get(ch, 0) + 1
    for ch in str1:
        if count[ch] == 1:
            return ch
    return None
