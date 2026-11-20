FAMILIES = {
    "packaging":{
        "manual":"packaging.version.parse(text). Input object has one key text, an ASCII string of length 1..50. The observation is the returned Python class name or, if it raises, the exception class name. The workloads mix ordinary and unconventional software versions. Common outcome names include Version, LegacyVersion, InvalidVersion.",
        "history":[{"text":"1.0"},{"text":"v2.3"},{"text":"vendor-nightly"}],
        "tests":[[{"text":"2026.8rc1"},{"text":"upstream-latest"},{"text":"1.5+dev.2"},{"text":"Blue_Build"}],
                 [{"text":"branch-Z"},{"text":"3.1.post2"},{"text":"urgent patch"},{"text":"v4.9"}]]},
    "PyJWT":{
        "manual":"PyJWT jwt.decode is called on a fresh, valid HS256 token whose only claim is sub=label, using the correct secret. Input object: label (ASCII string length 1..50) and algorithms (one of the strings omit, HS256, HS384). omit leaves the keyword out; otherwise pass algorithms=[that string]. Our wrapper returns OK for decoded claims, otherwise the Python exception class name. Common outcomes include OK, DecodeError, InvalidAlgorithmError.",
        "history":[{"label":"a","algorithms":"HS256"},{"label":"b","algorithms":"HS384"},{"label":"c","algorithms":"omit"}],
        "tests":[[{"label":"dawn","algorithms":"omit"},{"label":"fog","algorithms":"HS256"},{"label":"haze","algorithms":"HS384"},{"label":"sun","algorithms":"omit"}],
                 [{"label":"auger","algorithms":"HS384"},{"label":"lathe","algorithms":"omit"},{"label":"saw","algorithms":"omit"},{"label":"clamp","algorithms":"HS256"}]]},
    "more-itertools":{
        "manual":"more_itertools.chunked(values, n, ...) is fully consumed. Input object: values (a list of 0..12 integers from -99..99), n (an integer 1..8), strict (JSON true, false, or the string omit). omit leaves the strict keyword out, otherwise pass it as given. Our wrapper returns OK when iteration completes, otherwise the Python exception class name. Common outcomes include OK, TypeError, ValueError.",
        "history":[{"values":[1,2,3],"n":2,"strict":"omit"},{"values":[1,2],"n":2,"strict":"omit"},{"values":[2,3,5],"n":2,"strict":True}],
        "tests":[[{"values":[4,7,9,11],"n":2,"strict":True},{"values":[8,2,5],"n":2,"strict":True},{"values":[1,5,9],"n":2,"strict":False},{"values":[3,9,14],"n":2,"strict":"omit"}],
                 [{"values":[2,4,6,8],"n":3,"strict":True},{"values":[3,6,9],"n":3,"strict":"omit"},{"values":[7,7,7],"n":3,"strict":True},{"values":[],"n":5,"strict":False}]]},
}


def accepted(name,x):
    if not isinstance(x,dict):
        return False
    def string(v):
        return isinstance(v,str) and v.isascii() and 1<=len(v)<=50
    if name=="packaging":
        return set(x)=={"text"} and string(x["text"])
    if name=="PyJWT":
        return set(x)=={"label","algorithms"} and string(x["label"]) and x["algorithms"] in ("omit","HS256","HS384")
    return (set(x)=={"values","n","strict"} and isinstance(x["values"],list) and len(x["values"])<=12
            and all(type(v) is int and abs(v)<=99 for v in x["values"])
            and type(x["n"]) is int and 1<=x["n"]<=8 and (type(x["strict"]) is bool or x["strict"]=="omit"))
