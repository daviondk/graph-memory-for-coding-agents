def pancake_sort(nums):
    """
    Sort a list of elements using pancake sort.
    
    Pancake sort works by repeatedly finding the maximum unsorted element
    and flipping it to the end of the unsorted portion.
    """
    n = len(nums)
    if n <= 1:
        return nums
    
    # Work on a copy to avoid modifying the original
    arr = nums[:]
    
    for size in range(n, 1, -1):
        # Find the index of the maximum element in arr[0:size]
        max_idx = 0
        for i in range(1, size):
            if arr[i] > arr[max_idx]:
                max_idx = i
        
        # If the maximum element is not already at the end of the unsorted portion
        if max_idx != size - 1:
            # Flip the array from 0 to max_idx to bring the max to the front
            arr[0:max_idx + 1] = reversed(arr[0:max_idx + 1])
            # Flip the array from 0 to size-1 to bring the max to its correct position
            arr[0:size] = reversed(arr[0:size])
    
    return arr
