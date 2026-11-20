def words_string(s):
    if not s:
        return []
    
    s = s.replace(',', ' ')
    return s.split()
