"""Count how often gold lies in a boundary tie; stable author ordering is the recorded primary setting."""
from full_java import *
from collections import defaultdict
from data_io import rows
def run(task):
    file,start,end=task;p=D/"archive_inputs"/file;stats=np.zeros((5,5));pf=pq.ParquetFile(p);loc=0
    crop=author_function("repo_author_utils.py","crop_code_lines");sim=author_function("repo_author_similarity.py","jaccard_similarity");tok=Adapter()
    for rg in range(pf.num_row_groups):
        nr=pf.metadata.row_group(rg).num_rows
        if loc+nr<=start:loc+=nr;continue
        if loc>=end:break
        ix=loc
        for batch in pf.iter_batches(batch_size=32,row_groups=[rg],columns=["code","context","gold_snippet_index"]):
            for row in batch.to_pylist():
                idx=ix;ix+=1
                if not start<=idx<end:continue
                q=crop(row["code"],3);ss=np.array([sim(q,x,tok) for x in row["context"]]);gold=row["gold_snippet_index"];z=ss[gold];better=int(np.sum(ss>z));equal=int(np.sum(ss==z));rank=better+int(np.sum(ss[:gold]==z))+1
                for t,k in enumerate((1,3,5)):
                    low=int(better+equal<=k);high=int(better<k);stats[t]+=[int(rank<=k),low,high,min(1,max(0,(k-better)/equal)),int(high!=low)]
        loc+=nr
    return panel_name(p.stem),stats.tolist()
def main():
    paths=sorted((D/"archive_inputs").glob("*.parquet"));todo=[]
    for p in paths:
        n=pq.ParquetFile(p).metadata.num_rows
        for j in range(0,n,1500):todo.append((p.name,j,min(j+1500,n)))
    out=defaultdict(lambda:np.zeros((5,5)))
    with ProcessPoolExecutor(4) as pool:
        for panel,a in pool.map(run,todo):out[panel]+=a
    write("archive_tie_audit.json",{"columns":["stable_hits","worst_tie_hits","best_tie_hits","uniform_random_tiebreak_expected_hits","gold_boundary_ties"],"rows":["@1","@3","@5"],"sums":{k:v[:3].tolist() for k,v in out.items()}})
if __name__=="__main__":main()
