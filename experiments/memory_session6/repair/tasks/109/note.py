def odd_Equivalent(s, n):
    """
    Count rotations of binary string s with odd integer value.
    
    Args:
        s: A binary string (e.g., "1011")
        n: Length of the string (should equal len(s))
    
    Returns:
        Number of rotations of s that have an odd integer value.
    """
    if not s or n == 0:
        return 0
    
    # A binary number is odd if and only if its last bit is 1.
    # For a rotation, the last bit of the rotated string corresponds to
    # the bit at position (i - 1) mod n in the original string, where i is
    # the rotation index (rotating left by i positions).
    #
    # More precisely: if we rotate left by k positions, the resulting string
    # is s[k:] + s[:k]. The last character of this rotated string is s[k-1]
    # (with k-1 mod n).
    #
    # So the rotated string is odd iff s[(k-1) % n] == '1'.
    #
    # This means the count of odd rotations equals the count of '1's in s.
    
    return s.count('1')
