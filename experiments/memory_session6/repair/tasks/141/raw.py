def pancake_sort(nums):
    """
    Sort a list of elements using pancake sort.
    
    Pancake sort works by repeatedly finding the maximum element in the unsorted
    portion and flipping it to the end.
    """
    n = len(nums)
    for size in range(n, 1, -1):
        # Find the index of the maximum element in the first 'size' elements
        max_idx = 0
        for i in range(1, size):
            if nums[i] > nums[max_idx]:
                max_idx = i
        
        # If the maximum element is not already at the end of the unsorted portion
        if max_idx != size - 1:
            # Flip the array from index 0 to max_idx to bring the max to the front
            nums[0:max_idx + 1] = reversed(nums[0:max_idx + 1])
            # Flip the array from index 0 to size-1 to bring the max to its correct position
            nums[0:size] = reversed(nums[0:size])
    
    return nums
