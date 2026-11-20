from pathlib import Path
import hashlib,json,requests,zipfile,io,csv
ROOT=Path(__file__).resolve().parent
WEST='https://raw.githubusercontent.com/westermo/test-results-dataset/31ca0ab802fd2eecf3455c6622c2c18f5b3fe775/'
ABB='https://raw.githubusercontent.com/mregorova/RETECS/9980ab6035f7a961c56e3b33e202bf2c18d15e6f/'
def main():
    raw=ROOT/'raw';raw.mkdir(exist_ok=True);data={}
    for filename,url in [('west.zip',WEST+'data/test-results.zip'),('paintcontrol.csv',ABB+'DATA/paintcontrol.csv'),('iofrol.csv',ABB+'DATA/iofrol.csv'),('WEST_LICENSE',WEST+'LICENSE'),('ABB_LICENSE',ABB+'LICENSE')]:
        dest=raw/filename
        if not dest.exists():
            response=requests.get(url,timeout=120);response.raise_for_status();dest.write_bytes(response.content)
        b=dest.read_bytes();data[filename]={'url':url,'sha256':hashlib.sha256(b).hexdigest(),'bytes':len(b)}
    (ROOT/'source.json').write_text(json.dumps(data,indent=2))
    with zipfile.ZipFile(raw/'west.zip') as z:
        print(z.namelist())
        with z.open(next(n for n in z.namelist() if n.endswith('test-results.csv'))) as f:print(f.readline(),f.readline()[:300])
    for file in ['paintcontrol.csv','iofrol.csv']:
        with (raw/file).open() as f:print(file,f.readline(),f.readline()[:140])
if __name__=='__main__':main()
