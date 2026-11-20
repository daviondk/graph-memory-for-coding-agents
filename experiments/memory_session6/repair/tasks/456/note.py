def reverse_string_list(stringlist):
    """
    Reverse each string in the input list.
    
    Args:
        stringlist: A list of strings.
        
    Returns:
        A new list with each string reversed.
    """
    return [s[::-1] for s in stringlist]
