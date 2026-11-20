```python
def lps(s: str) -> str:
    """
    Return the longest palindromic subsequence string.
    If multiple exist, return any. Empty input returns empty string.
    Case-sensitive matching applies.
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
    # We need to find the actual characters, not just the length
    # Use a recursive/iterative approach to build the string
    
    def build(i: int, j: int) -> str:
        if i > j:
            return ""
        if i == j:
            return s[i]
        if s[i] == s[j]:
            if i + 1 == j:
                return s[i] + s[j]
            return s[i] + build(i + 1, j - 1) + s[j]
