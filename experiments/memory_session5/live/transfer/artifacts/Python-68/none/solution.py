def pluck(arr):
    if len(arr) == 0:
        return []
    evens = [(val, idx) for idx, val in enumerate(arr) if val % 2 == 0]
    if not evens:
        return []
    min_val = min(val for val, _ in evens)
    min_idx = next(idx for val, idx in evens if val == min_val)
    return [min_val, min_idx]
