def snake_to_camel(word):
    if not word:
        return ""
    parts = word.split('_')
    # Filter out empty strings that might result from leading/trailing underscores
    parts = [p for p in parts if p]
    if not parts:
        return ""
    # Capitalize the first letter of each part and join
    return parts[0] + ''.join(p.capitalize() for p in parts[1:])
