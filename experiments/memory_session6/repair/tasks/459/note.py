import re

def remove_uppercase(str1: str) -> str:
    """Remove all uppercase letters from the given string using regex."""
    if not str1:
        return str1
    return re.sub(r'[A-Z]', '', str1)
