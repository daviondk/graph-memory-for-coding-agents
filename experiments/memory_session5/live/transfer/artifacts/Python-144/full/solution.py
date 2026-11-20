def simplify(x, n):
    a, b = x.split("/")
    c, d = n.split("/")
    a, b, c, d = int(a), int(b), int(c), int(d)
    numerator = a * c
    denom = b * d
    return numerator % denom == 0
