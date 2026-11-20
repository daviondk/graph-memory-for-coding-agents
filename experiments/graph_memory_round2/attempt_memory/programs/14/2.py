def find_Volume(l, b, h):
    """
    Calculate the volume of a triangular prism.
    
    The volume of a triangular prism is given by:
    V = (1/2) * base * height_of_triangle * length
    
    Here, we assume:
    - l is the length of the prism
    - b is the base of the triangular face
    - h is the height of the triangular face
    
    Parameters:
    l (float): length of the prism
    b (float): base of the triangular face
    h (float): height of the triangular face
    
    Returns:
    float: volume of the triangular prism
    """
    return 0.5 * b * h * l
