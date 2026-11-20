def histogram(test):
    if not test:
        return {}
    
    words = test.split(" ")
    
    # Filter out empty strings if any (though split by space on non-empty string shouldn't produce them unless multiple spaces)
    # But the problem says "space separated lowercase letters", so we assume single spaces.
    # However, if test is "a  b", split gives ['a', '', 'b']. We should probably ignore empty strings.
    # Let's count only non-empty strings.
    
    counts = {}
    for word in words:
        if word:  # Ignore empty strings
            if word in counts:
                counts[word] += 1
            else:
                counts[word] = 1
    
    if not counts:
        return {}
    
    max_count = max(counts.values())
    
    result = {}
    for word, count in counts.items():
        if count == max_count:
            result[word] = count
    
    return result
