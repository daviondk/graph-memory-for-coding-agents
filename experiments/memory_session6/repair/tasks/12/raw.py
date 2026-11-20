def sort_matrix(M):
    """
    Sort a given matrix in ascending order according to the sum of its rows.
    
    Args:
        M: A list of lists representing the matrix.
        
    Returns:
        A new matrix with rows sorted by their sum in ascending order.
    """
    return sorted(M, key=lambda row: sum(row))
