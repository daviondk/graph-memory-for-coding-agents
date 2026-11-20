from pathlib import Path
import sys
Q=Path(__file__).resolve().parent
WORK=Q.parents[1];R10=WORK/'graph_memory_round10'/'multiset';R9=WORK/'graph_memory_round9'
sys.path.insert(0,str(R10));sys.path.append(str(R9/'budget'))
from common import load,put,sha