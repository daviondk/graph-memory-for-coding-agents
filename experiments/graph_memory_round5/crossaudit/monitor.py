from pathlib import Path
import subprocess,sys,time,json
d=Path(__file__).resolve().parent;c=d.parent/'crosscode'
while not all((c/f'{p}_decisions.json').is_file() for p in ('D','E')):time.sleep(10)
for script in ['independent.py','audit_report.py']:
    with (d/(script+'.log')).open('w',encoding='utf8') as out:
        subprocess.run([sys.executable,str(d/script)],stdout=out,check=True,cwd=d)
print('Independent audit completed.',flush=True)

