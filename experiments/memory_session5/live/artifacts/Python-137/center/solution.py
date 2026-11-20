def compare_one(a, b):
    def to_float(x):
        if isinstance(x, str):
            return float(x.replace(',', '.'))
        return float(x)
    fa, fb = to_float(a), to_float(b)
    if fa > fb:
        return a
    if fb > fa:
        return b
    return None
    if float(temp_a) == float(temp_b): return None
    return a if float(temp_a) > float(temp_b) else b 
