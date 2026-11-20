def reverse_string_list(stringlist):
    """
    Reverse each string in the given list of strings.
    
    Args:
        stringlist: A list of strings.
        
    Returns:
        A new list where each string is reversed.
    """
    return [s[::-1] for s in stringlist]
