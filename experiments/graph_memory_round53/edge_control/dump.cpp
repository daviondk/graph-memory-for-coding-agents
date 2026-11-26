// Export all observed passage-address candidates using the frozen full-directory scorer.
#define main prior_retrieval_main
#include "../../graph_memory_round52/global_titles/retrieval.cpp"
#undef main
#include <iomanip>
struct Mention { size_t first=0, length=0, times=0; bool href=false; };
int main(int argc,char** argv) {
    if(argc!=2)return 1;
    Corpus c; std::string base=argv[1];
    std::ifstream qi(base+"/questions.in"),pi(base+"/second.in"); std::string a,b;
    std::cout<<std::setprecision(17);
    while(std::getline(qi,a)) {
        if(!std::getline(pi,b))return 2;
        std::istringstream qin(a),pin(b);std::string q,other;Doc seed;size_t nh;
        qin>>q;pin>>other>>seed>>nh;if(q!=other)return 3;
        auto qt=integers(qin);std::unordered_map<Doc,Mention> all;
        for(size_t j=0;j<nh;j++){Doc d;pin>>d;if(d==seed)return 4;all[d].href=true;}
        auto pt=integers(pin);auto joint=c.terms(qt,pt);
        for(size_t i=0;i<pt.size();i++) {
            uint32_t node=0;
            for(size_t j=i;j<pt.size();j++){
                auto it=c.children.find((uint64_t(node)<<32)|pt[j]);if(it==c.children.end())break;
                node=it->second;
                for(Doc d=c.trie[node].head;d!=NONE;d=c.next[d])if(d!=seed) {
                    auto& m=all[d];if(m.times==0){m.first=i;m.length=j-i+1;}m.times++;
                }
            }
        }
        std::vector<Doc> ids;for(auto &e:all)ids.push_back(e.first);std::sort(ids.begin(),ids.end());
        std::cout<<q;
        for(Doc d:ids){auto m=all[d];std::cout<<'\t'<<d<<','<<c.page[d]<<','<<c.score(d,joint)<<','<<m.first<<','<<m.length<<','<<m.times<<','<<m.href;}
        std::cout<<'\n';
    }
    return std::getline(pi,b)?5:0;
}
