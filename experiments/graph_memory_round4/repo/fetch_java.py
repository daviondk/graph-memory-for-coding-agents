from pathlib import Path
import sys
R3=Path(__file__).resolve().parents[2]/"graph_memory_round3/repo"
src=(R3/"fetch.py").read_text("utf8")
src=src.replace("o['path'].startswith('python_')","o['path'].startswith('java_')")
src=src.replace('or "/train_hard/0000"','or "/train_hard/0000"')
exec(compile(src,str(__file__),"exec"))
