from pathlib import Path
import hashlib,json,urllib.request
D=Path(__file__).resolve().parent
REV='40c68d2b7ca2a8eae95d901ac80e6a540a84a53d'
remote={'eval_metric.py':'scripts/eval_metric.py','eval_utils.py':'scripts/eval_utils.py','java.txt':'scripts/keywords/java.txt','keywordlist.py':'scripts/keywords/keywordlist.py','requirements.txt':'requirements.txt'}
info={}
for name,path in remote.items():
    url=f'https://raw.githubusercontent.com/amazon-science/cceval/{REV}/{path}'
    data=urllib.request.urlopen(url).read();(D/name).write_bytes(data)
    info[name]={'url':url,'sha256':hashlib.sha256(data).hexdigest()}
(D/'upstream.json').write_text(json.dumps(info,indent=2))

