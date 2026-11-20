def first_non_repeating_character(str1):
    from collections import OrderedDict
    counts = {}
    for ch in str1:
        counts[ch] = counts.get(ch, 0) + 1
    for ch in str1:
        if counts[ch] == 1:
            return ch
    return None
