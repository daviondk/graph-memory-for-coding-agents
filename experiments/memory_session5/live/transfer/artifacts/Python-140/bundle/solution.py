def fix_spaces(text):
    new_text = ""
    i = 0
    while i < len(text):
        if text[i] == " ":
            count = 0
            while i < len(text) and text[i] == " ":
                count += 1
                i += 1
            if count > 2:
                new_text += "-"
            else:
                new_text += "_" * count
        else:
            new_text += text[i]
            i += 1
    return new_text
