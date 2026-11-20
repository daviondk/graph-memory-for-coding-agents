def search(lst):
    from collections import Counter
    freq = Counter(lst)
    ans = -1
    for num, count in freq.items():
        if count >= num and num > ans:
            ans = num
    return ans
