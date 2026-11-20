def first_non_repeating_character(str1):
    from collections import OrderedDict
    char_count = OrderedDict()
    for ch in str1:
        if ch in char_count:
            char_count[ch] += 1
        else:
            char_count[ch] = 1
    for ch, count in char_count.items():
        if count == 1:
            return ch
    return None
