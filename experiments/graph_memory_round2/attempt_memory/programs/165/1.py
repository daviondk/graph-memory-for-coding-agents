def count_char_position(str1):
    count = 0
    for i, ch in enumerate(str1):
        if ch.isalpha():
            if ch.lower() == chr(ord('a') + i):
                count += 1
    return count
