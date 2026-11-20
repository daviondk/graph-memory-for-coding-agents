def extract_freq(test_list):
    """
    Extract the frequency of unique tuples in the given list, order irrespective.
    
    Args:
        test_list: A list of tuples.
        
    Returns:
        A dictionary where keys are unique tuples and values are their frequencies.
    """
    freq = {}
    for item in test_list:
        if item in freq:
            freq[item] += 1
        else:
            freq[item] = 1
    return freq
