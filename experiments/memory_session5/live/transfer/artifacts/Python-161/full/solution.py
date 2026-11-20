def solve(s):
    has_letter = any(c.isalpha() for c in s)
    if not has_letter:
        return s[::-1]
    return ''.join(c.swapcase() if c.isalpha() else c for c in s)
