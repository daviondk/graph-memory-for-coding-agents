from typing import List


def string_xor(a: str, b: str) -> str:
    result = []
    for i in range(max(len(a), len(b))):
        bit_a = a[i] if i < len(a) else '0'
        bit_b = b[i] if i < len(b) else '0'
        if bit_a == bit_b:
            result.append('0')
        else:
            result.append('1')
    return ''.join(result)
    return ''.join(xor(x, y) for x, y in zip(a, b))
