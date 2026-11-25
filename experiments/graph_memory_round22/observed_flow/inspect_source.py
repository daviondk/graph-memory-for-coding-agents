"""Schema inventory only; no attribution predictions or reference comparisons."""
from collections import Counter
from sources import D,C,read
def main():
    locks=read(D/'source-lock.json')
    for repo in sorted({r['repo'] for r in locks}):
        typ=Counter(); etyp=Counter(); vtypes=Counter(); shape=Counter()
        paths=[]
        for r in locks:
            if r['repo']!=repo or r['bytes']==0: continue
            try: obj=read(C/(r['git_blob']+'.json'))
            except (ValueError,UnicodeError):shape['invalid_json']+=1;continue
            for k,z in obj.items():
                if k in ('activity','entity','used','wasGeneratedBy'):shape[k+':'+type(z).__name__]+=1
            if not isinstance(obj.get('activity'),dict):continue
            for n,z in obj['activity'].items():typ.update([str(z.get('rdt:type',z.get('type','MISSING')))])
            for n,z in obj['entity'].items():
                etyp.update([str(z.get('rdt:type',z.get('type','MISSING')))])
                if z.get('rdt:type')=='Data':vtypes.update([(type(z.get('rdt:value')).__name__,str(z.get('rdt:valType',''))[:55])])
            paths.append((r['path'],len(obj['activity']),len(obj['entity']),len(obj.get('used',{}))))
        print(repo,shape,typ.most_common(7),etyp.most_common(9),vtypes.most_common(4),paths[:3])
if __name__=='__main__':main()

