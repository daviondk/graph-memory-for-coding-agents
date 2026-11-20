```python
def magic_square_test(my_matrix):
    """
    Verify if input matrix is a magic square.
    Return boolean. Handle non-square, negative, or non-integer inputs as invalid.
    """
    # Check if input is a list of lists
    if not isinstance(my_matrix, list) or len(my_matrix) == 0:
        return False
    
    n = len(my_matrix)
    
    # Check if it's a square matrix
    for row in my_matrix:
        if not isinstance(row, list) or len(row) != n:
            return False
    
    # Check all elements are positive integers
    for row in my_matrix:
        for val in row:
            if not isinstance(val, int) or isinstance(val, bool) or val <= 0:
                return False
    
    # Calculate the magic constant (sum of first row)
    magic_sum = sum(my_matrix[0])
    
    # Check all rows
    for row in my_matrix:
        if sum(row) != magic_sum:
            return False
    
    # Check all columns
    for col in range(n):
        col_sum = sum(my_matrix[row][col] for row in range(n))
        if col_sum != magic_sum:
            return False
    
    # Check main diagonal
    main_diag_sum = sum(my_matrix[i][i] for i in range(n))
    if main_diag_sum != magic_sum:
        return False
    
    # Check anti-diagonal
    anti_diag_sum = sum(my_matrix[i][n - 1 - i] for i in range(n))
    if anti_diag_sum != magic_sum:
        return False
    
    # Check that all numbers are unique and from 1 to n^2
    all_numbers = [val for row in my_matrix for val in row]
    if len(set(all_numbers)) != n * n:
        return False
    if min(all_numbers)
