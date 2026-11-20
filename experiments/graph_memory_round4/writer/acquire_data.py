"""Reuse the identical R3 pairing/projection rules and 48 MiB transport bound."""
from pathlib import Path
import sys
D=Path(__file__).resolve().parent
sys.path.insert(0,str(D.parents[1]/"graph_memory_round3/real_swe"))
import acquire
if __name__=="__main__":
    acquire.D=D
    acquire.main()
