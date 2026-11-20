def pluck(arr):
    if(len(arr) == 0): return []
    evens = list(filter(lambda x: x%2 == 0, arr))
    if(evens == []): return []
    min_val = min(evens)
    return [min_val, arr.index(min_val)]
