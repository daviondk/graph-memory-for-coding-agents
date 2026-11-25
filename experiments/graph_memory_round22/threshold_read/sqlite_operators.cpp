#include <algorithm>
#include <chrono>
#include <cstdint>
#include <limits>
#include <memory>
#include <stdexcept>
#include <vector>

extern "C" {
struct sqlite3;
struct sqlite3_stmt;
int sqlite3_open_v2(const char*, sqlite3**, int, const char*);
int sqlite3_close(sqlite3*);
int sqlite3_exec(sqlite3*, const char*, int (*)(void*,int,char**,char**), void*, char**);
int sqlite3_prepare_v2(sqlite3*, const char*, int, sqlite3_stmt**, const char**);
int sqlite3_finalize(sqlite3_stmt*);
int sqlite3_bind_int(sqlite3_stmt*, int, int);
int sqlite3_step(sqlite3_stmt*);
int sqlite3_reset(sqlite3_stmt*);
int sqlite3_column_int(sqlite3_stmt*, int);
int sqlite3_stmt_status(sqlite3_stmt*, int, int);
int sqlite3_db_status(sqlite3*, int, int*, int*, int);
}

namespace {
constexpr int row=100;
constexpr int done=101;
constexpr int ok=0;
constexpr int readonly=1;
constexpr int vm_step=4;
constexpr int cache_hit=7;
constexpr int cache_miss=8;

struct Connection {
    sqlite3* db=nullptr;
    sqlite3_stmt* rank=nullptr;
    sqlite3_stmt* sql_sort=nullptr;
    sqlite3_stmt* materialized=nullptr;
    ~Connection() {
        if(rank) sqlite3_finalize(rank);
        if(sql_sort) sqlite3_finalize(sql_sort);
        if(materialized) sqlite3_finalize(materialized);
        if(db) sqlite3_close(db);
    }
};
struct Item { double score; int rank; int unit; };
struct Lower {
    bool operator()(const Item& a,const Item& b) const {
        return a.score==b.score ? a.rank>b.rank : a.score<b.score;
    }
};
struct Packing {
    int left;
    bool skip;
    int n;
    const std::int64_t* costs;
    const std::int64_t* cheapest;
    int* output;
    int count=0;
    int cost_pos=0;
    std::vector<unsigned char> used;
    Packing(int budget,bool gaps,int size,const std::int64_t* price,const std::int64_t* by_cost,int* target):
        left(budget),skip(gaps),n(size),costs(price),cheapest(by_cost),output(target),used(skip ? size : 0,0) {}
    bool accept(int unit) {
        if(costs[unit]<=left) {
            output[count++]=unit;
            left-=static_cast<int>(costs[unit]);
            if(!left) return true;
        } else if(!skip) {
            return true;
        }
        if(skip) {
            used[unit]=1;
            while(cost_pos<n && used[cheapest[cost_pos]]) ++cost_pos;
            if(cost_pos==n || costs[cheapest[cost_pos]]>left) return true;
        }
        return false;
    }
};
int page_counter(sqlite3* db,int counter,int reset) {
    int current=0,high=0;
    if(sqlite3_db_status(db,counter,&current,&high,reset)!=ok) throw std::runtime_error("SQLite cache counter");
    return current;
}
int get_node(sqlite3_stmt* statement,int n,int& reads) {
    int result=sqlite3_step(statement);
    if(result==done) return -1;
    if(result!=row) throw std::runtime_error("SQLite step");
    int unit=sqlite3_column_int(statement,0);
    if(unit<0 || unit>=n) throw std::runtime_error("Invalid unit");
    ++reads;
    return unit;
}
}

extern "C" __declspec(dllexport) void* memory_open(const char* file) {
    auto conn=std::make_unique<Connection>();
    if(sqlite3_open_v2(file,&conn->db,readonly,nullptr)!=ok) return nullptr;
    if(sqlite3_exec(conn->db,"PRAGMA query_only=ON; PRAGMA cache_size=-65536",nullptr,nullptr,nullptr)!=ok) return nullptr;
    if(sqlite3_prepare_v2(conn->db,"select unit from dense where q=? order by r",-1,&conn->rank,nullptr)!=ok) return nullptr;
    if(sqlite3_prepare_v2(conn->db,"select d.unit,p.cost from dense d join prior p on p.t=? and p.unit=d.unit where d.q=? order by d.g+p.value desc,d.r",-1,&conn->sql_sort,nullptr)!=ok) return nullptr;
    if(sqlite3_prepare_v2(conn->db,"select unit,cost from final where q=? order by k",-1,&conn->materialized,nullptr)!=ok) return nullptr;
    return conn.release();
}
extern "C" __declspec(dllexport) void memory_close(void* handle) {
    delete static_cast<Connection*>(handle);
}
extern "C" __declspec(dllexport) int memory_query(
    void* handle,int mode,int q,int t,int n,int skip,int budget,const double* signal,const double* upper,
    const double* prior,const std::int64_t* costs,const std::int64_t* by_prior,const std::int64_t* by_cost,
    int* output,std::int64_t* observation) {
    if(!handle || n<1 || budget<0 || mode<0 || mode>4) return -1;
    auto* conn=static_cast<Connection*>(handle);
    auto* statement=(mode==3 ? conn->sql_sort : mode==4 ? conn->materialized : conn->rank);
    try {
        sqlite3_stmt_status(statement,vm_step,1);
        page_counter(conn->db,cache_hit,1);
        page_counter(conn->db,cache_miss,1);
        auto begin=std::chrono::steady_clock::now();
        if(sqlite3_bind_int(statement,1,mode==3 ? t : q)!=ok ||
            (mode==3 && sqlite3_bind_int(statement,2,q)!=ok)) throw std::runtime_error("SQLite bind");
        int reads=0,scored=0;
        Packing pack(budget,skip!=0,n,costs,by_cost,output);
        if(budget>0 && mode<2) {
            std::vector<Item> all;
            all.reserve(n);
            for(int rank=0;rank<n;++rank) {
                int unit=get_node(statement,n,reads);
                if(unit<0) throw std::runtime_error("Incomplete Dense list");
                all.push_back({signal[rank]+prior[unit],rank,unit});++scored;
            }
            if(mode==0) {
                std::sort(all.begin(),all.end(),[](const Item& a,const Item& b){return Lower{}(b,a);});
                for(const Item& v:all) if(pack.accept(v.unit)) break;
            } else {
                std::make_heap(all.begin(),all.end(),Lower{});
                while(!all.empty()) {
                    int unit=all.front().unit;
                    std::pop_heap(all.begin(),all.end(),Lower{});all.pop_back();
                    if(pack.accept(unit)) break;
                }
            }
        } else if(budget>0 && mode==2) {
            std::vector<unsigned char> visited(n,0);
            std::vector<Item> heap;
            int first=0;
            bool finished=false;
            for(int rank=0;rank<n && !finished;++rank) {
                int unit=get_node(statement,n,reads);
                if(unit<0) throw std::runtime_error("Incomplete Dense list");
                visited[unit]=1;heap.push_back({signal[rank]+prior[unit],rank,unit});++scored;
                std::push_heap(heap.begin(),heap.end(),Lower{});
                while(first<n && visited[by_prior[first]]) ++first;
                double bound=first==n || rank+1==n ? -std::numeric_limits<double>::infinity() : upper[rank+1]+prior[by_prior[first]];
                while(!heap.empty() && heap.front().score>bound) {
                    int current=heap.front().unit;
                    std::pop_heap(heap.begin(),heap.end(),Lower{});heap.pop_back();
                    if(pack.accept(current)) {finished=true;break;}
                }
            }
        } else if(budget>0) {
            while(true) {
                int unit=get_node(statement,n,reads);
                if(unit<0 || pack.accept(unit)) break;
            }
        }
        if(sqlite3_reset(statement)!=ok) throw std::runtime_error("SQLite reset");
        auto end=std::chrono::steady_clock::now();
        observation[0]=reads;
        observation[1]=scored;
        observation[2]=sqlite3_stmt_status(statement,vm_step,0);
        observation[3]=page_counter(conn->db,cache_hit,0);
        observation[4]=page_counter(conn->db,cache_miss,0);
        observation[5]=std::chrono::duration_cast<std::chrono::nanoseconds>(end-begin).count();
        return pack.count;
    } catch(...) {
        sqlite3_reset(statement);
        return -1;
    }
}

