def sort_matrix(M):
    """
    Sort matrix rows by ascending sum. Return new matrix.
    Handle empty matrix and non-rectangular inputs gracefully.
    """
    if not M:
        return []
    
    # Validate that M is a list of lists (or at least iterable of iterables)
    # For non-rectangular inputs, we just sort by sum of each row
    rows = []
    for row in M:
        try:
            s = sum(row)
        except TypeError:
            # If row is not iterable or contains non-numeric, skip or handle
            # We'll treat it as having sum 0 or skip? Let's be graceful: skip invalid rows
            continue
        rows.append((s, row))
    
    # Sort by sum
    rows.sort(key=lambda x: x[0])
    
    # Return new matrix with just the rows
    return [row for _, row in rows]
