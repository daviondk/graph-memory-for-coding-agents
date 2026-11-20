"""After scoring, locate where the same eight-file exploration loses a repair site."""
import ast,collections,gzip,json,tarfile
from driver import D,read


def main():
    cases=[];ct=collections.Counter()
    for r in read(D/'cpu_rows.json'):
        task=D/'tasks'/r['id'];p=json.loads(gzip.decompress((task/'packets.json.gz').read_bytes()))
        sites={(path,n) for path,n in r['sites']};candidate=set()
        with tarfile.open(task/'checkout.tar.gz','r:gz') as tar:
            for member in tar:
                path=member.name.partition('/')[2]
                if path not in p['paths'] or not member.isfile():continue
                source=tar.extractfile(member).read().decode('utf8',errors='replace')
                try:tree=ast.parse(source)
                except (SyntaxError,ValueError):continue
                def walk(nodes):
                    for node in nodes:
                        if isinstance(node,ast.ClassDef):walk(node.body)
                        elif isinstance(node,(ast.FunctionDef,ast.AsyncFunctionDef)):
                            candidate.update((path,n) for n in range(node.lineno,node.end_lineno+1))
                walk(tree.body)
        kept={a:{(path,n) for path,lo,hi in p['kept'][a] for n in range(lo,hi+1)} for a in ('flat','evidence')}
        group='no_gold_in_files' if not r['visible'] else 'outside_function_blocks' if not candidate&sites else 'ranked_out' if not kept['flat']&sites else 'hit'
        ct[group]+=1;ct['admissible_gold_lines']+=len(candidate&sites)
        ct['different_gold_coordinates']+=int((kept['flat']&sites)!=(kept['evidence']&sites))
        cases.append(dict(id=r['id'],group=group,admissible_gold_lines=len(candidate&sites),new_gold=sorted((kept['evidence']-kept['flat'])&sites),lost_gold=sorted((kept['flat']-kept['evidence'])&sites)))
    (D/'diagnosis.json').write_text(json.dumps(dict(counts=ct,cases=cases),indent=1));print(ct)


if __name__=='__main__':main()
