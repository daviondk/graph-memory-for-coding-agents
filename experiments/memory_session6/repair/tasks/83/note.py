def get_Char(strr):
    if not strr:
        return 0
    return sum(ord(c) for c in strr)
