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
        "finally", "ultimately", "initially", "originally", "previously",
        "recently", "lately", "soon", "now", "then", "here", "there",
        "where", "when", "how", "why", "what", "which", "who", "whom",
        "up", "down", "in", "out", "on", "off", "over", "under", "through",
        "across", "along", "around", "behind", "before", "between", "beyond",
        "during", "except", "inside", "outside", "toward", "towards",
        "away", "back", "forth", "forward", "backward", "backwards",
        "upward", "upwards", "downward", "downwards", "sideways",
        "inward", "inwards", "outward", "outwards", "onward", "onwards",
        "hence", "therefore", "thus", "so", "henceforth", "henceforward",
        "meanwhile", "nevertheless", "nonetheless", "otherwise", "instead",
        "likewise", "similarly", "accordingly", "consequently", "accordingly",
        "indeed", "certainly", "surely", "probably", "possibly", "perhaps",
        "maybe", "perhaps", "undoubtedly", "unquestionably", "indisputably",
        "unmistakably", "undeniably", "incontestably", "irrefutably",
        "unambiguously", "unequivocally", "explicitly", "implicitly",
        "directly", "indirectly", "immediately", "instantaneously",
        "simultaneously", "concurrently", "contemporaneously",
        "subsequently", "priorly", "previously", "afterwards", "hereafter",
        "herein", "hereof", "hereunto", "hereupon", "thereafter", "therein",
        "thereof", "thereunto", "thereupon", "whereafter", "wherein",
        "whereof", "whereunto", "whereupon", "wherewith", "wherewithal",
        "whence", "whither", "whenceforth", "whitherward",
        "ever", "forever", "evermore", "everlasting", "eternally",
        "perpetually", "incessantly", "continuously", "constantly",
        "steadily", "uniformly", "consistently", "regularly", "periodically",
        "intermittently", "sporadically", "irregularly", "
