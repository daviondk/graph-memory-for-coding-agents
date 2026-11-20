"""Six bounded tool contracts. The scorer and observation server execute these functions."""
import re
from datetime import date


# Each row has the public contract, a routine historical input, 3 historical
# edge inputs, and 4 NEW inputs for each of the 3 edges plus common behavior.
# Input values in the evaluation bank are withheld until after the probe.
FAMILIES = {
    "decimal": {
        "manual": "Input: one string. Default: if the entire string consists of one or more ASCII digits, return its nonnegative integer value; otherwise return null. At most one optional change may be active: permit a single leading plus sign; allow single underscores between digits; or strip surrounding ASCII spaces before validation. No other input cleanup occurs.",
        "routine": "123", "edges": ["+17", "1_7", " 17 "],
        "tests": [["+41", "+82", "+509", "+004"], ["2_9", "35_6", "7_5_1", "00_9"], [" 42", "86 ", " 90 ", " 002 "], ["91", "530", "77", "003"]]},
    "dates": {
        "manual": "Input: one string. Default: accept a real calendar date in exactly YYYY-MM-DD with two-digit month and day and return its ISO YYYY-MM-DD string; else return null. At most one additional syntax may be active: YYYY/MM/DD; YYYY.MM.DD; or YYYYMMDD. A deployment supports either just the default or the default plus one listed syntax.",
        "routine": "2024-01-02", "edges": ["2024/02/14", "2024.02.14", "20240214"],
        "tests": [["2025/03/02","2031/12/29","2028/02/29","2017/10/04"],["2021.04.01","2026.06.17","2019.11.29","2028.02.29"],["20230228","20190611","20240921","20201002"],["2017-05-12","2020-03-21","2015-12-04","2030-02-17"]]},
    "suffix": {
        "manual": "Input: one ASCII basename (no directories). Default: lowercase the substring after the last dot, or return an empty string if there is no dot after the first character. At most one change may be active: recognize a terminal .tar.gz case-insensitively as the compound extension tar.gz; treat a leading dot in an otherwise dot-free nonempty name as an extension separator; or preserve the original letter case of the ordinary extension.",
        "routine": "photo.jpg", "edges": ["pkg.tar.gz", ".env", "index.HTML"],
        "tests": [["a.tar.gz","src.tar.gz","mesh.tar.gz","cache.tar.gz"],[".ignore",".config",".trace",".profile"],["q.PDF","bin.DLL","p.jPeG","sample.Ts"],["out.jar","a.tmp","README","run.log"]]},
    "length": {
        "manual": "Input: one Unicode string. Default: return the number of Unicode code points. At most one change may be active: count each CRLF pair as one; count each non-BMP character as two; or exclude all U+0300 through U+036F combining marks from the count. Return an integer.",
        "routine": "alpha", "edges": ["x\r\ny", "x🌏y", "xe\u0301y"],
        "tests": [["ab\r\nc","\r\nQ","k\r\nl\r\nm","zz\r\n"],["Q🐍","🧩xx","ab😊cd","🥝🥝"],["y\u0302","e\u0301tt","aa\u0301b\u0300","x\u0300x"],["Hi","ßx","XYZ","snow"]]},
    "slug": {
        "manual": "Input: one ASCII string. Default: lowercase ASCII letters, preserve digits, and replace EACH character outside [a-z0-9] by one hyphen with no trimming or collapsing. At most one change may be active before default processing: drop dots; preserve underscores verbatim; or expand each plus sign to the word plus. Output a string.",
        "routine": "Desk7", "edges": ["m.n", "m_n", "m+n"],
        "tests": [["Ab.Z","p.q","File.7","a..b"],["Blue_Red","a__b","P_0","Yo_"],["R+D","a+b","9+4","Z++"],["ABC","Hi 7","Q9","a!b"]]},
    "bucket": {
        "manual": "Input: one integer from -1000 through 1000. Default: return floor(input / 10), including for negative values. At most one change may be active: assign positive exact multiples of ten to the preceding bucket; clip all negative inputs to zero before computing; or clip values above 99 to 99 before computing. Output an integer.",
        "routine": 35, "edges": [20, -21, 127],
        "tests": [[30,40,70,80],[-12,-5,-31,-47],[109,128,151,211],[23,57,69,1]]},
}


def execute(family, mode, value):
    if family == "bucket":
        if type(value) is not int or abs(value) > 1000:
            raise ValueError("expected an integer from -1000 through 1000")
        if mode == 1 and value > 0 and value % 10 == 0:
            return value // 10 - 1
        if mode == 2:
            value = max(value, 0)
        if mode == 3:
            value = min(value, 99)
        return value // 10
    if type(value) is not str or len(value) > 64:
        raise ValueError("expected a string of no more than 64 code points")
    if family in ("suffix", "slug") and not value.isascii() and value:
        raise ValueError("expected ASCII")
    if family == "suffix":
        if "/" in value or "\\" in value:
            raise ValueError("expected basename")
        if mode == 1 and value.lower().endswith(".tar.gz"):
            return "tar.gz"
        pos = value.rfind(".")
        if pos < 0 or (pos == 0 and mode != 2):
            return ""
        suffix = value[pos + 1:]
        return suffix if mode == 3 else suffix.lower()
    if family == "decimal":
        if mode == 1:
            value = value.removeprefix("+")
        if mode == 2 and re.fullmatch(r"[0-9]+(?:_[0-9]+)*", value):
            value = value.replace("_", "")
        if mode == 3:
            value = value.strip(" ")
        return int(value) if re.fullmatch(r"[0-9]+", value) else None
    if family == "dates":
        patterns = [r"([0-9]{4})-([0-9]{2})-([0-9]{2})", r"([0-9]{4})/([0-9]{2})/([0-9]{2})",
                    r"([0-9]{4})\.([0-9]{2})\.([0-9]{2})", r"([0-9]{4})([0-9]{2})([0-9]{2})"]
        for idx in set((0,mode)):
            match = re.fullmatch(patterns[idx], value)
            if match:
                try:
                    return date(*map(int,match.groups())).isoformat()
                except ValueError:
                    return None
        return None
    if family == "length":
        if mode == 1:
            return len(value.replace("\r\n","x"))
        if mode == 2:
            return sum(1 + (ord(ch) > 65535) for ch in value)
        if mode == 3:
            return sum(not (0x300 <= ord(ch) <= 0x36F) for ch in value)
        return len(value)
    if family == "slug":
        if mode == 1:
            value = value.replace(".","")
        if mode == 3:
            value = value.replace("+","plus")
        pattern = r"[^a-z0-9_]" if mode == 2 else r"[^a-z0-9]"
        return re.sub(pattern, "-", value.lower())
    raise KeyError(family)
