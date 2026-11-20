```python
import re


def find_adverb_position(text: str) -> list[tuple[str, int]]:
    """
    Find all adverbs and their positions in a sentence.
    
    Returns a list of (adverb, index) tuples where index is the starting
    position of the adverb in the original text.
    
    Handles punctuation, case sensitivity, and empty strings.
    """
    if not text:
        return []
    
    # Common adverbs (lowercase for matching)
    adverbs = {
        "quickly", "slowly", "happily", "sadly", "angrily", "carefully",
        "loudly", "quietly", "softly", "gently", "firmly", "strongly",
        "weakly", "brightly", "darkly", "early", "late", "often", "rarely",
        "always", "never", "sometimes", "usually", "frequently", "occasionally",
        "seldom", "hard", "fast", "well", "badly", "truly", "really",
        "very", "quite", "rather", "somewhat", "almost", "nearly", "exactly",
        "precisely", "clearly", "obviously", "certainly", "definitely",
        "absolutely", "completely", "entirely", "totally", "fully",
        "partly", "partially", "mostly", "mainly", "chiefly", "primarily",
        "largely", "greatly", "highly", "deeply", "sharply", "steeply",
        "gradually", "progressively", "increasingly", "decreasingly",
        "suddenly", "abruptly", "instantly", "immediately", "eventually",
        "
