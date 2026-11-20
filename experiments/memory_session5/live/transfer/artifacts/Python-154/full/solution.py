def cycpattern_check(a, b):
    if len(b) > len(a):
        return False
    pat = b + b
    for i in range(len(a) - len(b) + 1):
        for j in range(len(b)):
            if a[i:i+len(b)] == pat[j:j+len(b)]:
                return True
    return False
