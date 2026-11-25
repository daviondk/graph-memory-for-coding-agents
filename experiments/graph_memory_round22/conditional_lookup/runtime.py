"""Record the software and encoder files for the frozen CPU retrieval run."""
from importlib.metadata import version
import platform
from predict import MODEL
from prepare import ROOT, sha, dump
files = {p.name: sha(p.read_bytes()) for p in MODEL.iterdir() if p.is_file() and (p.suffix in (".json",".txt",".safetensors",".model"))}
dump(ROOT/"runtime.json", {"python": platform.python_version(), "runtime": platform.platform(),
     "libraries": {name: version(name) for name in ("numpy","torch","transformers","tokenizers")},
     "model_files": files, "device":"cpu", "threads":3, "dtype":"float32",
     "pooling":"L2 normalised mask-weighted mean", "max_input_tokens":512})

