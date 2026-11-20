#include <stdint.h>
#include <stdio.h>
#include <string.h>
#include <stdlib.h>
#include "libCacheSim.h"
#include "cache/eviction/S4FIFO.h"
#include "cache/eviction/S4FIFO_features.h"

extern bool S4FIFO_get_features(cache_t *, S4FIFO_feature_vector_t *);
extern int released_prediction(const S4FIFO_feature_vector_t *, int *,int *,int *,int *,double *);

static void adapt(cache_t *cache) {
    S4FIFO_feature_vector_t fv;
    if (!S4FIFO_get_features(cache,&fv)) exit(3);
    S4FIFO_base_params_t *p=(S4FIFO_base_params_t *)cache->eviction_params;
    int small,ghost,move,ghost_min;
    double skip;
    int valid=released_prediction(&fv,&small,&ghost,&move,&ghost_min,&skip);
    if(valid){
        p->small_size_ratio=small/100.0;
        p->ghost_size_ratio=ghost/100.0;
        p->move_to_main_threshold=move;
        p->ghost_to_main_threshold=ghost_min;
        p->small_skip_ratio=skip;
        p->small_fifo->cache_size=cache->cache_size*small/100;
        p->main_fifo->cache_size=cache->cache_size-p->small_fifo->cache_size;
        p->ghost_fifo->cache_size=cache->cache_size*ghost/100;
    }
    fprintf(stderr,"prediction valid=%d n=%lld hits=%lld small=%.2f ghost=%.2f move=%d ghost_min=%d skip=%.2f\n",
      valid,(long long)fv.total_requests,(long long)fv.total_hits,p->small_size_ratio,p->ghost_size_ratio,p->move_to_main_threshold,p->ghost_to_main_threshold,p->small_skip_ratio);
}

int main(int argc, char **argv){
    if(argc!=6) return 2;
    const char *algo=argv[1]; long cap=atol(argv[2]), boundary=atol(argv[3]);
    FILE *in=fopen(argv[4],"rb"), *out=fopen(argv[5],"wb");
    if(!in || !out) return 2;
    common_cache_params_t params={.cache_size=cap,.hashpower=18,.consider_obj_metadata=false};
    bool learned=strcmp(algo,"s4")==0;
    cache_t *cache;
    if(learned) cache=S4FIFO_init(params,"collect-features=true,feature-num-buckets=20,feature-collect-reqs=2147483647");
    else if(strcmp(algo,"lru")==0) cache=LRU_init(params,NULL);
    else if(strcmp(algo,"s3")==0) cache=S3FIFO_init(params,NULL);
    else return 2;
    request_t *r=new_request();r->obj_size=1;
    uint64_t start; uint32_t count; int64_t i=0,miss_first=0,miss_second=0;
    while(fread(&start,sizeof(start),1,in)==1){
        if(fread(&count,sizeof(count),1,in)!=1||count==0)return 4;
        if(i==boundary && learned) adapt(cache);
        uint32_t misses=0,group_reads=0;uint64_t last=UINT64_MAX;
        for(uint32_t j=0;j<count;j++){
            r->obj_id=start+j;
            if(cache->find(cache,r,false)==NULL){
                misses++;uint64_t group=r->obj_id/4;
                if(group!=last){group_reads++;last=group;}
            }
        }
        for(uint32_t j=0;j<count;j++){
            r->obj_id=start+j;
            cache->get(cache,r);
        }
        if(cache->get_n_obj(cache)>cap) return 5;
        if(i<boundary) miss_first+=misses;
        else miss_second+=misses;
        if(i>=boundary) {
            uint32_t row[]={group_reads,misses,count};
            if(fwrite(row,sizeof(uint32_t),3,out)!=3) return 4;
        }
        i++;
    }
    fprintf(stderr,"totals n=%lld boundary=%ld miss_pre=%lld miss_post=%lld\n",(long long)i,boundary,(long long)miss_first,(long long)miss_second);
    free_request(r);cache->cache_free(cache);fclose(out);fclose(in);return 0;
}
