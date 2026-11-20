def snake_to_camel(word):
    if not word:
        return ""
    parts = word.split('_')
    # Filter out empty strings that may result from leading/trailing underscores
    parts = [p for p in parts if p]
    if not parts:
        return ""
    # First part lowercased, rest capitalized
    result = parts[0].lower()
    for part in parts[1:]:
        result += part.capitalize()
    return result
