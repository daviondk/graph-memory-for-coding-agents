def count_Set_Bits(n):
    if n < 0:
        n = abs(n)
    return bin(n).count('1')
