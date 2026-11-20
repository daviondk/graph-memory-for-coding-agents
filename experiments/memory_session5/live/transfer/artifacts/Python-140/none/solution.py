def fix_spaces(text):
    new_text = ""
    i = 0
    space_count = 0
    while i < len(text):
        if text[i] == " ":
            space_count += 1
        else:
            if space_count > 2:
                new_text += "-"
            elif space_count > 0:
                new_text += "_" * space_count
            new_text += text[i]
            space_count = 0
        i += 1
    if space_count > 2:
        new_text += "-"
    elif space_count > 0:
        new_text += "_" * space_count
    return new_text
