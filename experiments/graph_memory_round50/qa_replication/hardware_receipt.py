import subprocess
from paths_repl import *

def main():
    pid=int((P/"qa.pid").read_text().strip())
    dev=subprocess.check_output(["nvidia-smi","--query-gpu=name,driver_version,memory.total,memory.used,utilization.gpu","--format=csv,noheader,nounits"],text=True).splitlines()[0]
    procs=subprocess.check_output(["nvidia-smi","--query-compute-apps=pid,process_name","--format=csv,noheader"],text=True).splitlines()
    assert any(row.split(",")[0].strip()==str(pid) and row.endswith("llama-server.exe") for row in procs)
    put(D/"hardware.json",dict(fields=["name","driver","vram_MiB","used_MiB","utilization_percent"],
        device=[x.strip() for x in dev.split(",")],own_binary="llama-server.exe"))
if __name__=="__main__":main()
