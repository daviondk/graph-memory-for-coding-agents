def cycpattern_check(a, b):
    if len(b) > len(a):
        return False
    pat = b + b
    for i in range(len(b)):
        if pat[i:i+len(b)] in a:
            return True
    return False
    return False
