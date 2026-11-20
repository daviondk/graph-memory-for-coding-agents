def is_sorted(lst):
    for i in range(1, len(lst)):
        if lst[i] < lst[i-1]:
            return False
        if lst[i] == lst[i-1] and i > 1 and lst[i-1] == lst[i-2]:
            return False
    return True
