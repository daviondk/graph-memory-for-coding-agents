def odd_Equivalent(s, n):
    """
    Find the number of numbers with an odd value when rotating a binary string the given number of times.
    
    Args:
        s: A binary string (e.g., "1011")
        n: Number of rotations to consider (rotations 0 to n-1)
    
    Returns:
        The count of rotations (from 0 to n-1) where the resulting binary number is odd.
    """
    if not s:
        return 0
    
    length = len(s)
    count = 0
    
    for i in range(n):
        # Rotate the string i times
        rotated = s[-i:] + s[:-i] if i > 0 else s
        # Check if the binary number is odd (last bit is '1')
        if rotated[-1] == '1':
            count += 1
    
    return count
