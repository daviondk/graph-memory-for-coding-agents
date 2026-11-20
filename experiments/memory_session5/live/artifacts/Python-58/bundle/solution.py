def common(l1: list, l2: list):
    ret = set(l1) & set(l2)
    return sorted(ret)
