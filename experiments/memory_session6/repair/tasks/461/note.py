def upper_ctr(s: str) -> int:
    if not isinstance(s, str):
        raise TypeError("Input must be a string")
    return sum(1 for c in s if 'A' <= c <= 'Z')
