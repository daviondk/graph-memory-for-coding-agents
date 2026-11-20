def sort_sublists(input_list):
    """
    Sort each sublist of strings in a list of lists using a lambda function.
    Return the modified list. Handle empty lists and sublists gracefully.
    """
    if not input_list:
        return input_list
    
    for i in range(len(input_list)):
        if input_list[i]:
            input_list[i].sort(key=lambda x: x)
    
    return input_list
