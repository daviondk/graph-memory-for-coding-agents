def is_sublist(l, s):
    """Return True if s is a contiguous subsequence of l."""
    if not s:
        return True
    n = len(l)
    m = len(s)
    if m > n:
        return False
    for i in range(n - m + 1):
        if l[i:i + m] == s:
            return True
    return False
