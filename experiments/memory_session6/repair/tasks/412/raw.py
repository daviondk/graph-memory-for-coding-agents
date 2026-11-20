def remove_odd(l):
    """
    Remove odd numbers from a given list.
    
    Args:
        l: A list of numbers
        
    Returns:
        A new list containing only the even numbers from the input list
    """
    return [x for x in l if x % 2 == 0]
