def test_duplicate(arraynums):
    """
    Return True if any integer appears more than once in the input array; otherwise return False.
    Handle empty arrays and single-element arrays correctly.
    """
    seen = set()
    for num in arraynums:
        if num in seen:
            return True
        seen.add(num)
    return False
