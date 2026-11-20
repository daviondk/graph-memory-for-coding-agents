from pathlib import Path
import sys
D=Path(__file__).resolve().parent
sys.path.insert(0,str(D.parent/"real_swe"))
import acquire
if __name__=="__main__":
    acquire.D=D;acquire.main()

