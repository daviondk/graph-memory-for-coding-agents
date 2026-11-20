from pathlib import Path
import hashlib,json
import urllib.request
ROOT=Path(__file__).resolve().parent
def main():
    name='restarted_builds.bson.gz'
    url='https://zenodo.org/records/3601137/files/'+name+'?download=1&full=x20'
    out=ROOT/name
    if not out.exists():
        data=urllib.request.urlopen(url,timeout=180).read()
        assert hashlib.md5(data).hexdigest()=='772a511ace2451c59055efd54e891659'
        out.write_bytes(data)
    data=out.read_bytes()
    assert hashlib.md5(data).hexdigest()=='772a511ace2451c59055efd54e891659'
    (ROOT/'source.json').write_text(json.dumps({'url':url,'doi':'10.5281/zenodo.3601137','name':name,'bytes':len(data),'sha256':hashlib.sha256(data).hexdigest(),'md5':hashlib.md5(data).hexdigest()},indent=2))
    print('Fetched',len(data),'bytes')
if __name__=='__main__':main()
