#include <algorithm>
#include <array>
#include <cassert>
#include <chrono>
#include <cmath>
#include <fstream>
#include <iomanip>
#include <iostream>
#include <numeric>
#include <vector>
using namespace std;
using Degree = array<int,8>;
using Meta = array<int,5>;
using Edge = array<int,3>;
struct Query { vector<int> order, expected; };
struct State { vector<Meta> put; vector<int> del; vector<Edge> minus,plus; vector<Query> q; vector<pair<int,double>> expected; };
using Trace=vector<State>;
array<double,23> weight; array<double,3> rankcoef; double bias,rankbias;
volatile long long sink=0;
using Counts=array<array<vector<int>,8>,2>;
struct Node { bool live=false; int role=0; Degree deg{}; double shape=0,score=0; int stamp=-1; };
struct Index {
    bool incremental; vector<Node> nodes;Counts bins{},prefix{};array<int,2> size{};int state=0;bool prepared=false;
    explicit Index(bool inc):incremental(inc){}
    void count(int r,int k,int d,int sign){
        auto &h=bins[r][k];if(d>=int(h.size()))h.resize(d+1);
        h[d]+=sign;assert(h[d]>=0);
    }
    void membership(Node& n,int sign){
        size[n.role]+=sign;
        if(incremental)for(int k=0;k<8;++k)count(n.role,k,n.deg[k],sign);
    }
    void change(int id,int k,int s){
        Node &n=nodes[id];auto &v=n.deg[k];assert(n.live && v+s>=0);
        if(incremental){count(n.role,k,v,-1);count(n.role,k,v+s,1);}v+=s;
    }
    void edge(Edge e,int sign){change(e[0],2*e[2],sign);change(e[1],2*e[2]+1,sign);}
    void update(const State& s){
        ++state;prepared=false;
        for(auto e:s.minus)edge(e,-1);
        for(int id:s.del){auto &n=nodes[id];membership(n,-1);n.live=false;}
        for(auto m:s.put){
            int id=m[0],role=m[1],tok=m[2],pos=m[3],len=m[4];
            if(id>=int(nodes.size()))nodes.resize(id+1);
            auto &n=nodes[id];if(n.live)membership(n,-1);
            n.live=true;n.role=role;
            n.shape=bias+weight[0]*role+weight[1]*log1p(tok)+weight[2]*log1p(pos)+weight[3]*double(pos)/max(1,len-1)
                     +weight[4]*(pos==0)+weight[5]*(pos==len-1)+weight[6]*log1p(len);
            membership(n,1);
        }
        for(auto e:s.plus)edge(e,1);
    }
    void prepare(){
        if(prepared)return;
        if(!incremental){
            for(auto &role:bins)for(auto &h:role)fill(h.begin(),h.end(),0);
            for(const auto &n:nodes)if(n.live)for(int k=0;k<8;++k)count(n.role,k,n.deg[k],1);
        }
        for(int r=0;r<2;++r)for(int k=0;k<8;++k){
            auto &h=bins[r][k];auto &p=prefix[r][k];p.resize(h.size());
            partial_sum(h.begin(),h.end(),p.begin());
        }
        prepared=true;
    }
    double prior(int id){
        Node &n=nodes[id];assert(n.live && prepared);
        if(n.stamp==state)return n.score;
        double v=n.shape;
        for(int k=0;k<8;++k){auto d=n.deg[k];auto r=n.role;
            v+=weight[7+k]*log1p(d);
            v+=weight[15+k]*((prefix[r][k][d]-.5*bins[r][k][d])/size[r]-.5);
        }
        n.stamp=state;return n.score=v;
    }
};
vector<int> ranked(Index& ix,const Query& q,int scope){
    int n=int(q.order.size()),lim=scope==0?n:min(8,n);vector<pair<double,int>> row;row.reserve(lim);
    for(int j=0;j<lim;++j){int r=j+1;
        double s=rankbias-rankcoef[0]*log(r)+rankcoef[1]/r+rankcoef[2]*(n-r)/max(1,n-1);
        row.emplace_back(-(ix.prior(q.order[j])+s),j);
    }
    sort(row.begin(),row.end());vector<int> ord;ord.reserve(lim);
    for(auto [s,j]:row)ord.push_back(j);
    return ord;
}
long long play(const Trace& tr,bool inc,int schedule,int scope){
    Index ix(inc);long long ret=0;
    for(int i=0;i<int(tr.size());++i){const State &st=tr[i];ix.update(st);
        if(schedule==0 || i+1==int(tr.size()) || (schedule==1&&(i+1)%4==0)){
            ix.prepare();
            for(auto &q:st.q){auto ord=ranked(ix,q,scope);ret+=ord.front();}
        }
    }
    return ret;
}
int main(int argc,char**argv){
    if(argc!=3)return 2;
    ifstream in(argv[1]);ofstream out(argv[2]);out<<setprecision(17);assert(in.good()&&out.good());
    for(auto &w:weight)in>>w;in>>bias;for(auto &v:rankcoef)in>>v;in>>rankbias;
    int ntr;in>>ntr;vector<Trace> traces(ntr);int nstate=0,nquery=0;double error=0;
    for(auto &tr:traces){
        int count;in>>count;tr.resize(count);Index a(true),b(false);
        for(auto &s:tr){
            int u,x,m,p,nq,nt;in>>u>>x>>m>>p>>nq>>nt;s.put.resize(u);s.del.resize(x);s.minus.resize(m);s.plus.resize(p);
            for(auto &r:s.put)for(int &v:r)in>>v;for(int &v:s.del)in>>v;
            for(auto &r:s.minus)for(int &v:r)in>>v;for(auto &r:s.plus)for(int &v:r)in>>v;
            s.expected.resize(nt);for(auto &v:s.expected)in>>v.first>>v.second;
            s.q.resize(nq);for(auto &q:s.q){int n;in>>n;q.order.resize(n);q.expected.resize(n);
                for(auto &v:q.order)in>>v;for(auto &v:q.expected)in>>v;}
            a.update(s);b.update(s);a.prepare();b.prepare();
            for(auto [v,y]:s.expected){auto x=a.prior(v);assert(x==b.prior(v));error=max(error,abs(x-y));}
            for(auto &q:s.q){assert(ranked(a,q,0)==q.expected && ranked(b,q,0)==q.expected);++nquery;}
            ++nstate;
        }
    }
    assert(in.good() && error<=1e-11);out<<"ok "<<nstate<<" "<<nquery<<" "<<error<<"\n";
    for(int t=0;t<ntr;++t)for(int f=0;f<3;++f)for(int scope=0;scope<2;++scope){
        for(int rep=0;rep<6;++rep)for(int i=0;i<2;++i){
            bool inc=(i+rep+t)%2;auto a=chrono::steady_clock::now();
            for(int k=0;k<10;++k)sink+=play(traces[t],inc,f,scope);
            auto b=chrono::steady_clock::now();
            if(rep)out<<t<<" "<<f<<" "<<scope<<" "<<int(inc)<<" "<<rep<<" "<<chrono::duration_cast<chrono::nanoseconds>(b-a).count()<<"\n";
        }
    }
}