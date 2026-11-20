def check_dict_case(dict):
    if len(dict.keys()) == 0:
        return False
    else:
        state = "start"
        for key in dict.keys():
            if isinstance(key, str) == False:
                state = "mixed"
                break
            if state == "start":
                if key.isupper():
                    state = "upper"
                elif key.islower():
                    state = "lower"
                else:
                    state = "mixed"
                    break
            elif state == "upper" and not key.isupper():
                state = "mixed"
                break
            elif state == "lower" and not key.islower():
                state = "mixed"
                break
        return state == "upper" or state == "lower"
