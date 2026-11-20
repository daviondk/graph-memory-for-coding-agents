def smallest_num(xs):
    if not xs:
        raise ValueError("List must not be empty")
    return min(xs)
