def move_one_ball(arr):
    if len(arr) == 0:
        return True
    
    # Count the number of times an element is greater than the next element
    # In a sorted array, this count should be 0.
    # In a rotated sorted array, this count should be exactly 1.
    # If the count is greater than 1, it's not a rotated sorted array.
    
    count = 0
    n = len(arr)
    
    for i in range(n):
        if arr[i] > arr[(i + 1) % n]:
            count += 1
            if count > 1:
                return False
    
    return True
