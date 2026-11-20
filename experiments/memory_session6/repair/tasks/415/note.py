def max_Product(arr):
    """
    Return the pair (as a tuple) with the maximum product from the array.
    
    Behavior:
    - If arr is empty, return (None, None).
    - If arr has one element, return (arr[0], arr[0]).
    - Otherwise, find the pair of distinct elements (by index) that yields the maximum product.
    
    Returns:
        A tuple (a, b) where a and b are elements from arr (at distinct indices) such that a*b is maximized.
    """
    if not arr:
        return (None, None)
    if len(arr) == 1:
        return (arr[0], arr[0])
    
    n = len(arr)
    max_prod = float('-inf')
    max_pair = (arr[0], arr[1])
    
    for i in range(n):
        for j in range(i + 1, n):
            prod = arr[i] * arr[j]
            if prod > max_prod:
                max_prod = prod
                max_pair = (arr[i], arr[j])
    
    return max_pair
