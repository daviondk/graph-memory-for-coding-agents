def ascii_value(k):
    if not isinstance(k, str):
        raise TypeError("Input must be a string")
    if len(k) != 1:
        raise TypeError("Input must be a single character")
    return ord(k)
