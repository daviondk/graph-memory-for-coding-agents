def freq_count(list1):
    freq = {}
    for item in list1:
        freq[item] = freq.get(item, 0) + 1
    return freq
