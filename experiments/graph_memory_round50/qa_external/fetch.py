"""Fetch pinned public evaluator source and the authors' data archive. No archive member is executed."""
import requests,zipfile
from paths50 import *
def main():
    check50();P50.mkdir(exist_ok=True)
    z=P50/"data_ids.zip"
    if not z.is_file():
        temp=P50/"data_ids.partial"
        with requests.get(OFF_URL,stream=True,timeout=(15,120)) as r,temp.open("wb") as f:
            r.raise_for_status()
            for b in r.iter_content(1<<20):f.write(b)
        temp.replace(z)
    with zipfile.ZipFile(z) as zd:
        relevant={Path(n).name:n for n in zd.namelist() if not n.startswith("__MACOSX") and Path(n).name in ("dev.json","id_aliases.json")}
        assert set(relevant)=={"dev.json","id_aliases.json"}
    url=f"https://raw.githubusercontent.com/Alab-NII/2wikimultihop/{AUTHOR_COMMIT}/2wikimultihop_evaluate_v1.1.py"
    r=requests.get(url,timeout=20);r.raise_for_status();(P50/"author_evaluate.py").write_bytes(r.content)
    put(D50/"official-source.json",dict(archive=sha(z),members=relevant,evaluator=sha(P50/"author_evaluate.py"),evaluator_url=url))
    print("official archive",relevant)
if __name__=="__main__":main()
