from source import *
def shape(x,depth=1):
    if isinstance(x,dict):return {k:shape(v,depth-1) if depth else type(v).__name__ for k,v in x.items()}
    if isinstance(x,list):return [shape(x[0],depth-1)] if x and depth else "list"
    return type(x).__name__
rr,_=cohort();seen=set()
for tab,col in [('handoffs','handoff_json'),('checkpoints','checkpoint_json'),('events','event_json'),('trajectories','event_json')]:
    f=next((P/'data'/tab).glob('*.parquet'));stats=Counter()
    for file in sorted((P/'data'/tab).glob('*.parquet')):
        for row in pq.read_table(file).to_pylist():
            run=row.get('run_id',row.get('initial_run_id'))
            if run not in rr:continue
            x=json.loads(row[col]) if row[col] else {};key=(tab,str(row.get('event_type',row.get('handoff_view'))),str(x.get('kind')) if isinstance(x,dict) else None)
            stats[key]+=1
            if key not in seen and len(seen)<35:
                seen.add(key);print(str(key)[:100],str(shape(x,1))[:630], 'run',run[:72])
    print(tab,len(stats),sum(stats.values()))

