def simplify(x, n):
    a, b = x.split("/")
    c, d = n.split("/")
    numerator = int(a) * int(c)
    denominator = int(b) * int(d)
    return numerator % denominator == 0
