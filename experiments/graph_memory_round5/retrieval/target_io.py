"""Read labels from a specified edition, concatenating its sorted physical shards per logical panel."""
from collections import Counter
from common5 import *
import pyarrow.parquet as pq

def target_rows(paths):
    offset=Counter()
    for path in sorted(paths):
        panel=path.stem.rsplit('_',1)[0]
        rows=pq.read_table(path,columns=['repo_name','gold_snippet_index']).to_pylist()
        for j,row in enumerate(rows,offset[panel]):
            yield (panel,j),(row['repo_name'],int(row['gold_snippet_index']))
        offset[panel]+=len(rows)

