from typing import List


def intersperse(numbers: List[int], delimeter: int) -> List[int]:
    if not numbers:
        return []

    result = []

    for i, n in enumerate(numbers):
        result.append(n)
        if i < len(numbers) - 1:
            result.append(delimeter)

    return result
