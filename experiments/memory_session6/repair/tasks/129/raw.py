def magic_square_test(my_matrix):
    """
    Check if the given matrix is a magic square.
    
    A magic square is a square matrix where the sum of each row, each column,
    and both main diagonals are equal.
    
    Args:
        my_matrix: A 2D list representing the matrix.
        
    Returns:
        True if the matrix is a magic square, False otherwise.
    """
    n = len(my_matrix)
    
    # Check if it's a square matrix
    if n == 0:
        return False
    for row in my_matrix:
        if len(row) != n:
            return False
    
    # Calculate the magic constant (sum of first row)
    magic_sum = sum(my_matrix[0])
    
    # Check all rows
    for i in range(n):
        if sum(my_matrix[i]) != magic_sum:
            return False
    
    # Check all columns
    for j in range(n):
        col_sum = sum(my_matrix[i][j] for i in range(n))
        if col_sum != magic_sum:
            return False
    
    # Check main diagonal
    diag1_sum = sum(my_matrix[i][i] for i in range(n))
    if diag1_sum != magic_sum:
        return False
    
    # Check anti-diagonal
    diag2_sum = sum(my_matrix[i][n - 1 - i] for i in range(n))
    if diag2_sum != magic_sum:
        return False
    
    return True
