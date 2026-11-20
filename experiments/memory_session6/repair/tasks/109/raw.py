def odd_Equivalent(s, n):
    """
    Find the count of rotations of a binary string with odd value.
    
    A binary string represents an odd number if and only if its last bit is '1'.
    For a rotation to have an odd value, the last character of the rotated string must be '1'.
    
    When we rotate the string, each character in the original string will end up in the last position
    exactly once across all n rotations. So the count of rotations with odd value equals the count of '1's in the string.
    
    Parameters:
    s: binary string
    n: length of the string (should equal len(s))
    
    Returns:
    Count of rotations that result in an odd value.
    """
    return s.count('1')
