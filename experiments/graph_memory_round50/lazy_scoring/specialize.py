"""Generate straight-line tree traversal using the exact frozen binary64 constants."""
from pathlib import Path
from time import perf_counter
import gzip
import hashlib
import json
import subprocess
import tempfile

D = Path(__file__).resolve().parent
M = D.parent / "matched_reader/model.json.gz"
LIB = D/"scoring.dll"

def expression(tree,i):
    f, threshold, left, right, value = tree[i]
    if left == right:
        return float(value).hex()
    a, b = expression(tree,left), expression(tree,right)
    return f"(x[{f}] <= {float(threshold).hex()} ? {a} : {b})"

def main():
    model = json.loads(gzip.decompress(M.read_bytes()))["trees"]
    statements = [f"  sum += {expression(tree,0)};" for tree in model["trees"]]
    scoring = f"static double compiled(const double* x) {{\n  double sum={float(model['base']).hex()};\n"
    scoring += "\n".join(statements) + "\n  return sum;\n}\n"
    program = scoring + (D/"kernel.cpp").read_text(encoding="utf8")
    start = perf_counter()
    with tempfile.TemporaryDirectory(dir=D) as tmp:
        path = Path(tmp)/"scoring.cpp"
        path.write_text(program,encoding="utf8")
        subprocess.run(["g++","-O3","-std=c++17","-ffp-contract=off","-shared","-static",str(path),"-o",str(LIB)],check=True)
    receipt = dict(model=hashlib.sha256(M.read_bytes()).hexdigest(),
        program=hashlib.sha256(program.encode()).hexdigest(),binary=hashlib.sha256(LIB.read_bytes()).hexdigest(),
        seconds=perf_counter()-start,compiler=subprocess.check_output(["g++","--version"],text=True).splitlines()[0])
    (D/"compiler.json").write_text(json.dumps(receipt,indent=2)+"\n",encoding="utf8")

if __name__ == "__main__":
    main()

