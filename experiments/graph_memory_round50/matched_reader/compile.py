from pathlib import Path
import os
import subprocess
D=Path(__file__).resolve().parent
subprocess.run(["g++","-O3","-std=c++17","-shared", "-static" if os.name=="nt" else "-fPIC","-ffp-contract=off",str(D/"select.cpp"),"-o",str(D/"kernels.dll")],check=True)

