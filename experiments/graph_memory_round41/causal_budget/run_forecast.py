from pathlib import Path
import time
from forecast_packets import D,forecast

if __name__=="__main__":
    for shard in range(8):
        deadline=time.monotonic()+600
        while not (D/f"state-{shard}-seal.json").exists():
            if time.monotonic()>deadline:
                raise TimeoutError(f"Missing state shard {shard}")
            time.sleep(2)
        for seed in (13,17,29,37,41):
            if not (D/f"pred-{seed}-{shard}-seal.json").exists():
                forecast(seed,[shard])

