def lps(s: str) -> str:
    """
    Find the longest palindromic subsequence in the given string.
    
    Args:
        s: Input string
        
    Returns:
        The longest palindromic subsequence
    """
    n = len(s)
    if n == 0:
        return ""
    
    # dp[i][j] will store the length of the longest palindromic subsequence
    # in s[i..j]
    dp = [[0] * n for _ in range(n)]
    
    # Every single character is a palindrome of length 1
    for i in range(n):
        dp[i][i] = 1
    
    # Fill the table for substrings of length 2 to n
    for length in range(2, n + 1):
        for i in range(n - length + 1):
            j = i + length - 1
            if s[i] == s[j]:
                if length == 2:
                    dp[i][j] = 2
                else:
                    dp[i][j] = dp[i + 1][j - 1] + 2
            else:
                dp[i][j] = max(dp[i + 1][j], dp[i][j - 1])
    
    # Now reconstruct the actual subsequence
    # We need to track the path
    result = []
    i, j = 0, n - 1
    left = []
    right = []
    
    while i < j:
        if s[i] == s[j]:
            left.append(s[i])
            right.append(s[j])
            i += 1
            j -= 1
        elif dp[i + 1][j] > dp[i][j - 1]:
            i += 1
        else:
            j -= 1
    
    if i == j:
        result.append(s[i])
    
    # Combine left, middle, and right
    result = left + result + right[::-1]
    
    return ''.join(result)
