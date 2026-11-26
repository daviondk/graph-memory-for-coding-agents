"""Fixed feature maps and causal replay for the two admission models."""
from collections import defaultdict
import math
import numpy as np
from build_inputs import D
LOCAL = ['input_tokens','in_current','was_resident','times_seen','gap','is_test','is_python',
         'first_line','interval_size','observed_by_state','depth']
GRAPH = ['opened_path','current_other_in_file','resident_other_in_file','shared_other_in_file',
         'added_other_in_file','dropped_other_in_file','sibling_jaccard','resident_interval_overlap']
N_LOCAL = len(LOCAL)


def scaled(n, ceiling):
    return math.log1p(max(0,min(n,ceiling)))/math.log1p(ceiling)


def overlap(start,end,other):
    a,b=other[2:4]
    if start<=0 or a<=0:return 0.
    return max(0,min(end,b)-max(start,a)+1)/max(1,max(end,b)-min(start,a)+1)


def candidates(resident, state, stage, graph=True):
    current=state['docs'];order=state['order'];keys=list(dict.fromkeys([*resident,*order]))
    old_files=defaultdict(set);new_files=defaultdict(set)
    if graph:
        for k,(record,n,last) in resident.items():old_files[record[1]].add(k)
        for k in order:new_files[current[k][1]].add(k)
    opened=set(state['opened']) if graph else set()
    rows=[];updated={}
    for k in keys:
        cur=k in current;old=k in resident
        previous,seen,last=resident.get(k,(None,0,stage))
        obj=current[k] if cur else previous
        n,path,start,end,test,py,vis=obj
        count=seen+int(cur)
        row=[n/512.,cur,old,scaled(count,12),scaled(stage-last,12) if old else 1.,test,py,
             scaled(start,2000),scaled(end-start+1,256),vis,scaled(stage,12)]
        if graph:
            past=old_files[path]-{k};present=new_files[path]-{k};both=past & present
            row.extend([int(path in opened),scaled(len(present),64),scaled(len(past),31),scaled(len(both),31),
                        scaled(len(present-past),64),scaled(len(past-present),31),len(both)/max(1,len(past|present)),
                        max((overlap(start,end,resident[x][0]) for x in past),default=0.)])
        rows.append(row)
        updated[k]=(obj,count,stage if cur else last)
    return keys,np.asarray(rows,dtype=np.float64),updated


def select(resident,state,stage,model,graph):
    keys,features,records=candidates(resident,state,stage,graph)
    logits=features@np.asarray(model['coef'])+model['intercept']
    probs=1/(1+np.exp(-np.clip(logits,-45,45)))
    order=sorted(zip(keys,probs),key=lambda x:(-round(float(x[1]*records[x[0]][0][0]),9),x[0]))
    return {k:records[k] for k,_ in order[:31]}


def retention(resident,unit):
    hits=unit['docs'].keys()&resident.keys()
    return [len(hits),sum(unit['docs'][k][0] for k in hits)]

