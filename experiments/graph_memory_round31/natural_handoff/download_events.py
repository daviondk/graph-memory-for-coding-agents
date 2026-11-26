from source import *
if __name__=="__main__":
    files=get(P/"files.json")["events"];start=time.perf_counter()
    with ThreadPoolExecutor(8) as ex:
        for j,path in enumerate(ex.map(fetch,files),1):
            if j%32==0:print(j,len(files),"seconds",round(time.perf_counter()-start,1),flush=True)
    save(D/"event-files.json",files);print(len(files),sum(x["bytes"] for x in files))

