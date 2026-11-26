"""Materialize a new independent timing workspace from signed inputs; requires SQLite dbstat and NumPy."""
import argparse
from pathlib import Path
from shutil import copyfile
import sqlite3
import subprocess
import sys
D=Path(__file__).resolve().parent
def main():
    ap=argparse.ArgumentParser();ap.add_argument('target',type=Path);args=ap.parse_args();w=args.target.resolve()
    if w.exists() or w.is_relative_to(D):raise ValueError('Choose a new directory outside the archived study')
    with sqlite3.connect(':memory:') as test:test.execute('SELECT count(*) FROM dbstat').fetchone()
    project=w/'graph_memory_round46/bounded_physical';a=w/'graph_memory_round44/sql_flow';b=w/'graph_memory_round45/bounded_counts'
    for p in (project,a,b):p.mkdir(parents=True)
    for src,dest in [('normalized.json.gz',a/'normalized.json.gz'),('r44-operators.py',a/'operators.py'),('r45-checks.json',b/'checks.json')]:
        copyfile(D/'inputs'/src,dest)
    for n in ('operators.py','run.py','analyze.py','interleave.py','cycle_stats.py','PROTOCOL_RU.md','INTERLEAVE_PROTOCOL_RU.md','COMPACT_PROTOCOL_RU.md','compact.py','compact_stats.py'):copyfile(D/n,project/n)
    (project/'inputs').mkdir();copyfile(D/'inputs/r45-per-trace.json.gz',project/'inputs/r45-per-trace.json.gz')
    for argv in [('run.py',),('analyze.py','--write'),('interleave.py',),('cycle_stats.py','--write'),('compact.py',),('compact_stats.py','--write')]:
        subprocess.run([sys.executable,'-B',*argv],cwd=project,check=True)
    print(project)
if __name__=='__main__':main()

