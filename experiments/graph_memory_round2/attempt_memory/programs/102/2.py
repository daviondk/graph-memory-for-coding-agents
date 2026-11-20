def snake_to_camel(word):
    if not word:
        return word
    parts = word.split('_')
    # Filter out empty strings that might result from leading/trailing underscores
    parts = [p for p in parts if p]
    if not parts:
        return ''
    first = parts[0].lower()
    rest = [p.capitalize() for p in parts[1:]]
    return first + ''.join(rest)
