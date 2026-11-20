def upper_ctr(s: str) -> int:
    """Count the number of uppercase characters in the given string."""
    return sum(1 for c in s if c.isupper())
