FIX = """
Add more test cases.
"""

def vowels_count(s):
    vowels = "aeiouAEIOU"
    n_vowels = sum(c in vowels for c in s)
    if s and s[-1] in "yY":
        n_vowels += 1
    return n_vowels
