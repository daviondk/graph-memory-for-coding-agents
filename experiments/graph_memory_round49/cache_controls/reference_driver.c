/* Calls the pinned library's public operations on unit-sized cache objects. */
#include "libCacheSim/evictionAlgo.h"
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

int main(int argc, char **argv) {
    if (argc != 2) return 2;
    common_cache_params_t p = default_common_cache_params();
    p.cache_size = 31;
    p.hashpower = 8;
    p.consider_obj_metadata = false;
    request_t *req = new_request();
    long long id;
    cache_t *c = NULL;
    while (scanf("%lld", &id) == 1) {
        if (id == -1) {
            if (c) c->cache_free(c);
            c = !strcmp(argv[1],"s3") ? S3FIFO_init(p,NULL) : Sieve_init(p,NULL);
            continue;
        }
        if (!c) return 3;
        int peek = id < -1;
        if (peek) id = -2-id;
        req->obj_id = id;
        req->obj_size = 1;
        int hit = peek ? c->find(c, req, false) != NULL : c->get(c, req);
        putchar(hit ? '1' : '0');
    }
    if (c) c->cache_free(c);
    free_request(req);
    putchar('\n');
    return 0;
}

