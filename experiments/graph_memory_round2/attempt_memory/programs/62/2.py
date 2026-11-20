def smallest_num(xs):
    if not xs:
        raise ValueError("Cannot find smallest number in an empty list")
    min_val = xs[0]
    for x in xs[1:]:
        if x < min_val:
            min_val = x
    return min_val
