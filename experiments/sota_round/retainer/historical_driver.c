#include "libCacheSim.h"
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

/* Each record in the native stream consists of the released ID and count=1. */
int main(int argc, char **argv) {
    if(argc!=6)return 2;
    FILE *src=fopen(argv[4],"rb"),*out=fopen(argv[5],"wb");
    if(!src||!out)return 2;
    long cap=atol(argv[2]),cut=atol(argv[3]);
    common_cache_params_t params={.cache_size=cap,.hashpower=20,.consider_obj_metadata=false};
    cache_t *cache;
    if(strcmp(argv[1],"s3")==0)cache=S3FIFO_init(params,NULL);
    else if(strcmp(argv[1],"lru")==0)cache=LRU_init(params,NULL);
    else if(strcmp(argv[1],"arc")==0)cache=ARC_init(params,NULL);
    else return 2;
    uint64_t k;uint32_t n;request_t *r=new_request();r->obj_size=1;
    int64_t pos=0,pre=0,post=0;
    while(fread(&k,sizeof(k),1,src)==1){
        if(fread(&n,sizeof(n),1,src)!=1||n!=1)return 3;
        r->obj_id=k;
        uint8_t miss=(uint8_t)!cache->get(cache,r);
        if(pos<cut)pre+=miss;
        else {post+=miss; if(fwrite(&miss,1,1,out)!=1)return 3;}
        pos++;
    }
    printf("n=%lld pre=%lld post=%lld\n",(long long)pos,(long long)pre,(long long)post);
    cache->cache_free(cache);free_request(r);fclose(out);fclose(src);return 0;
}
