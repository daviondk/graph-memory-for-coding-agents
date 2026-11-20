def pancake_sort(nums):
    """
    Sort a list in-place using prefix reversals (pancake sort).
    Return the sorted list.
    """
    if len(nums) <= 1:
        return nums
    
    def flip(arr, k):
        """Reverse the first k+1 elements of arr (0-indexed, so flip up to index k)."""
        arr[:k+1] = reversed(arr[:k+1])
    
    n = len(nums)
    for size in range(n, 1, -1):
        # Find the index of the maximum element in the first 'size' elements
        max_idx = 0
        for i in range(1, size):
            if nums[i] > nums[max_idx]:
                max_idx = i
        
        # If the max element is not already at the end of the current subarray
        if max_idx != size - 1:
            # Bring the max element to the front
            if max_idx != 0:
                flip(nums, max_idx)
            # Move it to the correct position
            flip(nums, size - 1)
    
    return nums
