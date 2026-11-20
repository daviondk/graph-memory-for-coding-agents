def find_lists(Input):
    """
    Return count of list objects in Input tuple.
    Handle empty tuples and nested structures by counting only direct list elements.
    """
    if not isinstance(Input, tuple):
        return 0
    count = 0
    for item in Input:
        if isinstance(item, list):
            count += 1
    return count
