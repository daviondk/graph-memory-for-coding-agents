#include <algorithm>
#include <chrono>
#include <cstdint>
#include <cstring>
#include <memory>
#include <stdexcept>
#include <vector>

extern "C" {
struct sqlite3;
struct sqlite3_stmt;
int sqlite3_open_v2(const char*,sqlite3**,int,const char*);
int sqlite3_close(sqlite3*);
int sqlite3_exec(sqlite3*,const char*,void*,void*,char**);
int sqlite3_prepare_v2(sqlite3*,const char*,int,sqlite3_stmt**,const char**);
int sqlite3_reset(sqlite3_stmt*);
int sqlite3_finalize(sqlite3_stmt*);
int sqlite3_step(sqlite3_stmt*);
int sqlite3_bind_int(sqlite3_stmt*,int,int);
int sqlite3_bind_double(sqlite3_stmt*,int,double);
int sqlite3_bind_blob(sqlite3_stmt*,int,const void*,int,void(*)(void*));
int sqlite3_column_int(sqlite3_stmt*,int);
int sqlite3_column_bytes(sqlite3_stmt*,int);
const void* sqlite3_column_blob(sqlite3_stmt*,int);
double sqlite3_column_double(sqlite3_stmt*,int);
int sqlite3_stmt_status(sqlite3_stmt*,int,int);
int sqlite3_db_status(sqlite3*,int,int*,int*,int);
}
namespace {
constexpr int row=100,done=101;
struct Block {
    double neg;
    int id,cost,event,lo,hi,padding;
    bool operator==(const Block& v)const{return neg==v.neg&&id==v.id&&cost==v.cost&&event==v.event&&lo==v.lo&&hi==v.hi;}
};
static_assert(sizeof(Block)==32);
bool before(const Block& a,const Block& b){return a.neg<b.neg||(a.neg==b.neg&&a.id<b.id);}
using Vector=std::vector<Block>;
bool eligible(const Block& a,const Vector& taken){
    for(auto& b:taken)if(a.event==b.event&&a.lo<b.hi&&b.lo<a.hi)return false;
    return true;
}
void check(int rc){if(rc!=0)throw std::runtime_error("SQLite");}
struct Conn {
    sqlite3* db=nullptr;
    enum {lookup,tail,cache,update_score,update_cache,count};
    sqlite3_stmt* st[count]{};
    ~Conn(){for(auto* p:st)if(p)sqlite3_finalize(p);if(db)sqlite3_close(db);}
    void prepare(int i,const char* sql){check(sqlite3_prepare_v2(db,sql,-1,&st[i],nullptr));}
    void command(const char* text){check(sqlite3_exec(db,text,nullptr,nullptr,nullptr));}
    int counter(int id,int reset){int current,hi;check(sqlite3_db_status(db,id,&current,&hi,reset));return current;}
};
Vector cache(Conn& c,int q,int b){
    auto* s=c.st[Conn::cache];check(sqlite3_bind_int(s,1,q));check(sqlite3_bind_int(s,2,b));
    if(sqlite3_step(s)!=row)throw std::runtime_error("No answer");
    int bytes=sqlite3_column_bytes(s,0);if(bytes%sizeof(Block))throw std::runtime_error("Invalid bytes");
    Vector v(bytes/sizeof(Block));if(bytes)std::memcpy(v.data(),sqlite3_column_blob(s,0),bytes);
    check(sqlite3_reset(s));return v;
}
void save(Conn& c,int q,int b,const Vector& v){
    auto* s=c.st[Conn::update_cache];static const unsigned char empty=0;
    const void* body=v.empty()?static_cast<const void*>(&empty):v.data();
    check(sqlite3_bind_blob(s,1,body,int(v.size()*sizeof(Block)),nullptr));
    check(sqlite3_bind_int(s,2,q));check(sqlite3_bind_int(s,3,b));
    if(sqlite3_step(s)!=done)throw std::runtime_error("Cache update");
    check(sqlite3_reset(s));
}
int remain(int b,const Vector& used){for(auto& x:used)b-=x.cost;return b;}
Vector scan(Conn& c,int q,int b,const Vector& core,const Vector& prefix,const Block* first,std::int64_t& rows){
    Vector used=core;used.insert(used.end(),prefix.begin(),prefix.end());int rest=remain(b,used);
    if(rest<0)throw std::runtime_error("Overbudget prefix");
    auto* s=c.st[first?Conn::tail:Conn::lookup];
    check(sqlite3_bind_int(s,1,q));if(first){check(sqlite3_bind_double(s,2,first->neg));check(sqlite3_bind_int(s,3,first->id));}
    while(rest>0){
        int v=sqlite3_step(s);if(v==done)break;if(v!=row)throw std::runtime_error("Read failure");++rows;
        int cost=sqlite3_column_int(s,2);if(cost>rest)continue;
        Block x{sqlite3_column_double(s,0),sqlite3_column_int(s,1),cost,sqlite3_column_int(s,3),sqlite3_column_int(s,4),sqlite3_column_int(s,5),0};
        if(eligible(x,used)){used.push_back(x);rest-=x.cost;}
    }
    check(sqlite3_reset(s));return Vector(used.begin()+core.size(),used.end());
}
bool unchanged(const Vector& prev,const Block* old,const Block* updates,int k,const Vector& core,int budget,bool check_geometry){
    for(const auto& selected:prev)for(int i=0;i<k;++i)if(old[i].id==selected.id)return false;
    Vector ns(updates,updates+k);std::sort(ns.begin(),ns.end(),before);
    Vector used=core;int left=remain(budget,used);size_t pos=0;
    for(const auto& x:ns){
        while(pos<prev.size()&&before(prev[pos],x)){left-=prev[pos].cost;used.push_back(prev[pos++]);}
        if(x.cost<=left&&(!check_geometry||eligible(x,used)))return false;
    }
    return true;
}
}
extern "C" __declspec(dllexport) void* packing_open(const char* p){
    auto c=std::make_unique<Conn>();try{
        check(sqlite3_open_v2(p,&c->db,2,nullptr));
        c->command("pragma cache_size=-49152; pragma mmap_size=0; pragma synchronous=FULL");
        c->prepare(Conn::lookup,"select neg,j,c,e,l,h from blocks indexed by idx_priority where q=? order by neg,j");
        c->prepare(Conn::tail,"select neg,j,c,e,l,h from blocks indexed by idx_priority where q=? and (neg,j)>=(?,?) order by neg,j");
        c->prepare(Conn::cache,"select body from packed where q=? and budget=?");
        c->prepare(Conn::update_score,"update blocks set neg=? where q=? and j=?");
        c->prepare(Conn::update_cache,"update packed set body=?1 where q=?2 and budget=?3 and body!=?1");
        return c.release();
    }catch(...){return nullptr;}
}
extern "C" __declspec(dllexport) void packing_close(void* h){delete static_cast<Conn*>(h);}
extern "C" __declspec(dllexport) int packing_run(void* handle,int method,int q,int budget,const Block* core_data,int ncore,
        const Block* old_data,const Block* updates,int n,int* output,std::int64_t* measures){
    auto& c=*static_cast<Conn*>(handle);
    try{
        Vector core(core_data,core_data+ncore);
        c.command("savepoint meas");
        for(auto* s:c.st)sqlite3_stmt_status(s,4,1);
        c.counter(7,1);c.counter(8,1);
        auto start=std::chrono::steady_clock::now();
        for(int i=0;i<n;++i){
            auto* s=c.st[Conn::update_score];check(sqlite3_bind_double(s,1,updates[i].neg));
            check(sqlite3_bind_int(s,2,q));check(sqlite3_bind_int(s,3,updates[i].id));
            if(sqlite3_step(s)!=done)throw std::runtime_error("update");check(sqlite3_reset(s));
        }
        auto updated=std::chrono::steady_clock::now();
        Vector chosen;std::int64_t reads=0;int path=0;
        if(method==0||n>32){
            chosen=scan(c,q,budget,core,{},nullptr,reads);save(c,q,budget,chosen);
        }else{
            auto prev=cache(c,q,budget);
            if(!n||unchanged(prev,old_data,updates,n,core,budget,method!=1)){chosen=prev;path=1;}
            else if(method!=3){chosen=scan(c,q,budget,core,{},nullptr,reads);save(c,q,budget,chosen);}
            else{
                Block first=old_data[0];for(int i=0;i<n;++i){if(before(updates[i],first))first=updates[i];if(before(old_data[i],first))first=old_data[i];}
                auto end=std::lower_bound(prev.begin(),prev.end(),first,before);
                chosen=scan(c,q,budget,core,Vector(prev.begin(),end),&first,reads);if(chosen!=prev)save(c,q,budget,chosen);
                path=2;
            }
        }
        auto finish=std::chrono::steady_clock::now();
        measures[0]=std::chrono::duration_cast<std::chrono::nanoseconds>(updated-start).count();
        measures[1]=std::chrono::duration_cast<std::chrono::nanoseconds>(finish-start).count();
        measures[2]=reads;measures[3]=0;for(auto* s:c.st)measures[3]+=sqlite3_stmt_status(s,4,0);
        measures[4]=c.counter(7,0);measures[5]=c.counter(8,0);measures[6]=path;
        for(size_t i=0;i<chosen.size();++i)output[i]=chosen[i].id;
        c.command("rollback to meas; release meas");
        return static_cast<int>(chosen.size());
    }catch(...){sqlite3_exec(c.db,"rollback",nullptr,nullptr,nullptr);return -1;}
}

