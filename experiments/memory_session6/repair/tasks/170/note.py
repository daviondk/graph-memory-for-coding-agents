def sum_range_list(list1, m, n):
    """
    Sum list elements from index m to n inclusive.
    Return 0 if m or n are out of bounds or m exceeds n.
    """
    if not list1:
        return 0
    if m < 0 or n < 0 or m >= len(list1) or n >= len(list1) or m > n:
        return 0
    return sum(list1[m:n+1])
