#include <cstdio>
#include <cstdint>
#include <cstddef>
#include <cmath>
#include <algorithm>
#include "cache/eviction/S4FIFO_features.h"
#include "types.h"
#include "S4FIFOLightGBMPredictor.h"

// Field names differ between the authors' simulation and production submodules.
extern "C" int released_prediction(const S4FIFO_feature_vector_t *s, int *small,
    int *ghost,int *move,int *ghost_min,double *skip){
    S4FIFOFeatureVector t;
    t.numBuckets=s->num_buckets;t.logCacheCapacity=s->log_cache_capacity;
    t.hitRatioSmall=s->hit_ratio_small;t.hitRatioMain=s->hit_ratio_main;
    t.hitRatioGhost=s->hit_ratio_ghost;t.uniqueRatio=s->unique_ratio;
    t.oneHitRatio=s->onehit_ratio;t.totalRequests=s->total_requests;
    t.totalHits=s->total_hits;t.totalMisses=s->total_misses;
    t.hitsSmall=s->hits_small;t.hitsMain=s->hits_main;t.hitsGhost=s->hits_ghost;
    std::copy_n(s->hist_small,t.numBuckets,t.histSmall);
    std::copy_n(s->hist_main,t.numBuckets,t.histMain);
    std::copy_n(s->hist_ghost,t.numBuckets,t.histGhost);
    auto p=lightGBMPredict(t);
    if(!p.hasAnyChange()) return 0;
    *small=p.tinySizePercent;*ghost=p.ghostSizePercent;*move=p.moveToMainThreshold;
    *ghost_min=p.ghostToMainThreshold;*skip=p.smallSkipRatio;
    return 1;
}
