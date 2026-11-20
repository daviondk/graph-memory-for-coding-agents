import re


def find_adverb_position(text: str) -> tuple:
    """
    Find the first adverb in the given sentence and return its position.
    
    Returns a tuple (adverb, start_index, end_index) where:
    - adverb is the first adverb found
    - start_index is the starting index of the adverb in the text
    - end_index is the ending index (exclusive) of the adverb in the text
    
    If no adverb is found, returns (None, -1, -1).
    
    Adverbs are identified as words ending in 'ly' (a common heuristic).
    """
    # Find all words and their positions
    words = re.finditer(r'\b\w+\b', text)
    
    for match in words:
        word = match.group()
        # Check if the word is an adverb (heuristic: ends with 'ly')
        if word.lower().endswith('ly') and len(word) > 2:
            return (word, match.start(), match.end())
    
    return (None, -1, -1)
