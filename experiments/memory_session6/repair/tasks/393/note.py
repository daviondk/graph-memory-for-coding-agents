def max_length_list(input_list):
    if not input_list:
        return None
    return max(input_list, key=lambda x: len(x))
