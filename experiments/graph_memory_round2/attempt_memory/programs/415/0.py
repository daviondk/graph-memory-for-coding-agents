def max_Product(arr):
    """
    Find a pair with the highest product from a given array of integers.
    
    Args:
        arr: List of integers
        
    Returns:
        A tuple (a, b) representing the pair with the highest product.
        If the array has fewer than 2 elements, returns (None, None).
    """
    if len(arr) < 2:
        return (None, None)
    
    max_prod = float('-inf')
    result = (None, None)
    
    for i in range(len(arr)):
        for j in range(i + 1, len(arr)):
            prod = arr[i] * arr[j]
            if prod > max_prod:
                max_prod = prod
                result = (arr[i], arr[j])
    
    return result
