def test_duplicate(arraynums):
    """
    Check if the given array of integers contains any duplicate element.
    
    Args:
        arraynums: A list of integers.
        
    Returns:
        True if there is at least one duplicate element, False otherwise.
    """
    seen = set()
    for num in arraynums:
        if num in seen:
            return True
        seen.add(num)
    return False
