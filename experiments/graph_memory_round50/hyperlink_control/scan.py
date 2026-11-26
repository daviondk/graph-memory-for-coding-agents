"""Stream the single DEFLATE member in source order using a bounded window of HTTP ranges."""
import binascii,concurrent.futures,json,re,struct,time,zlib
from collections import defaultdict
from urllib.request import Request,urlopen
from common import *
SIZE=1900740270
PAGE=8*1024*1024
N=6
HEADER=re.compile(rb'^\s*\{\s*"id"\s*:\s*(?:"[0-9]+"|[0-9]+)\s*,\s*"title"\s*:\s*("(?:[^"\\]|\\.)*")\s*,')
def fetch(args):
    a,b=args
    for retry in range(5):
        try:
            req=Request(URL,headers={"Range":f"bytes={a}-{b}","Accept-Encoding":"identity","User-Agent":"article-research/1"})
            with urlopen(req,timeout=45) as f:
                assert f.status==206 and f.headers.get("Content-Range")==f"bytes {a}-{b}/{SIZE}"
                data=f.read(b-a+2)
                assert len(data)==b-a+1
                return data
        except Exception:
            if retry==4:raise
            time.sleep(retry+1)
def ordered_ranges():
    blocks=[(i,min(i+PAGE,SIZE)-1) for i in range(0,SIZE,PAGE)]
    with concurrent.futures.ThreadPoolExecutor(N) as ex:
        pending={j:ex.submit(fetch,b) for j,b in enumerate(blocks[:N])}
        for j in range(len(blocks)):
            by=pending.pop(j).result()
            if j+N<len(blocks):pending[j+N]=ex.submit(fetch,blocks[j+N])
            yield by
def main():
    assert sha(D/"PROTOCOL_RU.md")=="893fea98e07d50e65f7ab7d770a8b9d627ce2ef86ab353c62168effbb0e5af8a"
    wanted,sources=candidates();ids=defaultdict(set);docs=defaultdict(list)
    total=0;uncompressed=0;crc=0;count=0;fallback=0;start=time.monotonic()
    raw=hashlib.sha256();journal=[];de=zlib.decompressobj(-15);rest=b""
    for j,block in enumerate(ordered_ranges()):
        raw.update(block);data=block;total+=len(block)
        if j==0:
            name,extra=struct.unpack_from("<HH",data,26)
            assert data[30:30+name]==b"para_with_hyperlink.jsonl"
            assert data[:4]==b"PK\x03\x04" and struct.unpack_from("<H",data,8)[0]==8
            wantcrc=struct.unpack_from("<I",data,14)[0]
            zipped=struct.unpack_from("<QQ",data,30+name+extra-16)
            data=data[30+name+extra:]
        while data and not de.eof:
            decoded=de.decompress(data,2*1024*1024)
            data=de.unconsumed_tail
            uncompressed+=len(decoded);crc=binascii.crc32(decoded,crc)
            lines=(rest+decoded).split(b"\n")
            rest=lines.pop()
            for line in lines:
                if not line:continue
                count+=1;m=HEADER.match(line);obj=None
                if m:n=title(json.loads(m[1]))
                else:
                    fallback+=1;obj=json.loads(line);n=title(obj["title"])
                if n not in wanted:continue
                if obj is None:obj=json.loads(line)
                ids[n].add(str(obj["id"]))
                if n in sources:docs[n].append([str(obj["id"]),obj["sentences"],obj["mentions"]])
        if (j+1)%32==0 or total==SIZE:
            row=[total,count,round(time.monotonic()-start,2),len(docs)];journal.append(row);print(row,flush=True)
    assert not rest and de.eof and total==SIZE and crc==wantcrc and zipped==(uncompressed,SIZE-308)
    write(PRIVATE/"titles.json.gz",{k:sorted(v) for k,v in ids.items()})
    write(PRIVATE/"sources.json.gz",docs)
    write(D/"source.json",{"url":URL,"zip_sha256":raw.hexdigest(),"compressed_archive":total,"member":"para_with_hyperlink.jsonl",
          "member_uncompressed":uncompressed,"member_deflated":zipped[1],"member_crc32":f"{crc:08x}","records":count,
          "title_parser_fallback":fallback,"catalog_titles":len(wanted),"source_titles":len(sources),"archive_catalog_titles":len(ids),
          "archive_source_titles":len(docs),"selected_sources":sha(PRIVATE/"sources.json.gz"),"selected_ids":sha(PRIVATE/"titles.json.gz"),"progress":journal})
if __name__=="__main__":main()

