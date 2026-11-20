import re
import string


def find_adverb_position(text: str) -> list:
    """
    Find all adverbs and their positions in a given sentence.
    
    Returns a list of tuples (adverb, start_position) where start_position
    is the index of the first character of the adverb in the text.
    
    Adverbs are identified as words ending in 'ly' (a common heuristic).
    """
    # Find all words and their positions
    words_with_positions = []
    for match in re.finditer(r'\b\w+\b', text):
        word = match.group()
        start = match.start()
        words_with_positions.append((word, start))
    
    # Filter for adverbs (words ending in 'ly')
    adverbs = []
    for word, start in words_with_positions:
        if word.lower().endswith('ly') and len(word) > 2:
            adverbs.append((word, start))
    
    return adverbs
