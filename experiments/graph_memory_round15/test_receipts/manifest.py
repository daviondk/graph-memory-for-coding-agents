from pathlib import Path
import json,hashlib
D=Path(__file__).resolve().parent
def manifest():
    return {p.relative_to(D).as_posix():hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(D.rglob("*"))
            if p.is_file() and p.name!="MANIFEST_SHA256.json" and "__pycache__" not in p.parts and not any(k.startswith(".grid-") for k in p.parts)}
if __name__=="__main__":
    f=D/"MANIFEST_SHA256.json"
    if f.exists():assert json.loads(f.read_bytes())==manifest()
    else:f.write_text(json.dumps(manifest(),indent=2,ensure_ascii=False),encoding="utf8")
    print(len(manifest()),sum((D/k).stat().st_size for k in manifest()))
