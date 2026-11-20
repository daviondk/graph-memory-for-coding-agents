from collections import defaultdict
import json,re
def decode_output(response,path,lo,width):
    if not response:
        return [None]*width
    # Consume only the delivered envelope. Capturing additional slice internals
    # here would grant the evaluator access to bytes the agent never saw.
    frame=json.loads(response.split('\n',2)[2].rsplit('\n',1)[0])
    found=defaultdict(list)
    def walk(item, inherited='', age=-1):
        if isinstance(item,list):
            for child in item:
                walk(child,inherited,age)
        elif isinstance(item,dict):
            location=item.get('path',inherited)
            age=item.get('observed_step',age)
            if location==path:
                bounds=item.get('line_range',[])
                if isinstance(bounds,str):
                    match=re.fullmatch(r'\s*(\d+)\s*->\s*(\d+)\s*',bounds)
                    bounds=list(map(int,match.groups())) if match else []
                text=item.get('code_excerpt',item.get('code'))
                if isinstance(text,str) and isinstance(bounds,list) and len(bounds)==2 and all(isinstance(v,int) for v in bounds):
                    # Every admitted input fragment includes the true terminal LF.
                    # A truncated last line without its LF is ambiguous and ignored.
                    complete=text.split('\n')[:-1]
                    for off,s in enumerate(complete[:bounds[1]-bounds[0]+1]):
                        found[bounds[0]+off].append((age,s))
            for k,v in item.items():
                if k=='content_json_excerpt' and isinstance(v,str):
                    try: extra=json.loads(v)
                    except (ValueError,TypeError): continue
                    walk(extra,location,age)
                elif isinstance(v,(dict,list)):
                    walk(v,location,age)
    walk(frame)
    answer=[]
    for n in range(lo,lo+width):
        if n not in found:
            answer.append(None)
            continue
        newest=max(age for age,_ in found[n])
        unique={s for age,s in found[n] if age==newest}
        answer.append(unique.pop() if len(unique)==1 else None)
    return answer


