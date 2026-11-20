"""Runs inside an isolated interpreter with only its stdlib and one unpacked distribution."""
import base64
import hashlib
import hmac
import json
from pathlib import Path
import sys
import warnings


def token(label):
    def segment(obj):
        data = json.dumps(obj,separators=(",",":")).encode()
        return base64.urlsafe_b64encode(data).rstrip(b"=")
    head = segment({"alg":"HS256","typ":"JWT"})
    body = segment({"sub":label})
    signed = head+b"."+body
    sig = hmac.new(b"controlled-pilot-key",signed,hashlib.sha256).digest()
    return signed+b"."+base64.urlsafe_b64encode(sig).rstrip(b"=")


def entry(package,path):
    if package == "packaging":
        from packaging import version as mod
        def call(x):
            return type(mod.parse(x["text"])).__name__
    elif package == "PyJWT":
        import jwt as mod
        def call(x):
            opt = {"algorithms":[x["algorithms"]]} if x["algorithms"]!="omit" else {}
            claims = mod.decode(token(x["label"]), b"controlled-pilot-key", **opt)
            assert claims == {"sub":x["label"]}
            return "OK"
    else:
        import more_itertools as mod
        def call(x):
            opt = {} if x["strict"]=="omit" else {"strict":x["strict"]}
            list(mod.chunked(x["values"],x["n"],**opt))
            return "OK"
    if not Path(mod.__file__).resolve().is_relative_to(path):
        raise RuntimeError(f"Unexpected module origin: {mod.__file__}")
    return call, str(Path(mod.__file__).relative_to(path))


if __name__ == "__main__":
    warnings.filterwarnings("ignore", category=DeprecationWarning)
    path = Path(sys.argv[1]).resolve()
    sys.path.insert(0,str(path))
    req = json.loads(sys.stdin.buffer.read())
    call, origin = entry(req["project"],path)
    out = []
    for x in req["inputs"]:
        try:
            result = call(x)
        except Exception as err:
            result = type(err).__name__
        out.append(result)
    print(json.dumps({"results":out, "module_origin_within_wheel":origin}))
