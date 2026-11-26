// Reuse the exact global catalogue/phrase and BM25 implementation. No second global search.
#define main native_retrieval_main
#include "../global_titles/retrieval.cpp"
#undef main
#include <array>
#include <set>

struct Span { Doc row; size_t begin,end; };
struct Gate {
    Doc winner=NONE;
    double best=-1;
    size_t count=0, begin=0, end=0, words=0, df=0;
};
std::vector<Span> matches(const Corpus& c, const std::vector<Word>& q) {
    std::vector<Span> spans;
    for(size_t i=0;i<q.size();++i) {
        uint32_t node=0;
        for(size_t j=i;j<q.size();++j) {
            auto it=c.children.find((uint64_t(node)<<32)|q[j]);
            if(it==c.children.end())break;
            node=it->second;
            for(Doc d=c.trie[node].head;d!=NONE;d=c.next[d])spans.push_back({d,i,j+1});
        }
    }
    return spans;
}
std::array<Gate,3> rank_direct(const Corpus& c,const std::vector<Word>& question,
                               Doc seed,const Terms& joint, size_t& sources) {
    std::array<Gate,3> gate;
    auto spans=matches(c,question);
    std::vector<bool> occupied(question.size(),false);
    for(auto s:spans) if(s.row==seed) {
        sources++;
        for(size_t i=s.begin;i<s.end;++i)occupied[i]=true;
    }
    if(!sources)return gate;
    std::set<Word> first(c.flat.begin()+c.start[seed],c.flat.begin()+c.start[seed+1]);
    std::array<std::set<Doc>,3> unique;
    for(auto s:spans) {
        if(s.row==seed||std::any_of(occupied.begin()+s.begin,occupied.begin()+s.end,[](bool a){return a;}))continue;
        std::set<Word> content;
        for(size_t j=s.begin;j<s.end;++j)if(!c.stop[question[j]])content.insert(question[j]);
        if(content.empty()||std::none_of(content.begin(),content.end(),[&](Word w){return !first.count(w);}))continue;
        size_t df=content.size()==1?c.lists[*content.begin()].size():0;
        std::array<size_t,3> limits{0,c.page.size()/100000,c.page.size()/1000};
        for(size_t i=0;i<gate.size();++i) {
            if(content.size()<2 && df>limits[i])continue;
            if(!unique[i].insert(s.row).second)continue;
            auto& g=gate[i];g.count++;
            double x=c.score(s.row,joint);
            if(x>g.best || (x==g.best&&c.better(s.row,g.winner))) {
                g.best=x;g.winner=s.row;g.begin=s.begin;g.end=s.end;g.words=content.size();g.df=df;
            }
        }
    }
    if(!(gate[0].count<=gate[1].count&&gate[1].count<=gate[2].count))throw std::runtime_error("non-nested gates");
    return gate;
}
int main(){
    Corpus c;
    std::ifstream questions("questions.in"),inputs("second.in"),seconds("second.tsv"),seeds("seed.tsv");
    std::ofstream out("policy52-direct.tsv");
    std::string line;size_t count=0;
    while(std::getline(questions,line)){
        std::istringstream a(line);std::string q;a>>q;auto qt=integers(a);
        std::string sl,il,fl;
        if(!std::getline(inputs,il)||!std::getline(seconds,sl)||!std::getline(seeds,fl))throw std::runtime_error("incomplete upstream cache");
        std::istringstream b(il),d(sl),f(fl);std::string id1,id2,id3;
        Doc src,ne,idx,first;b>>id1>>src>>ne;d>>id2>>idx;f>>id3>>first;
        if(id1!=q||id2!=q||id3!=q||src!=idx||src!=first)throw std::runtime_error("query/seed mismatch");
        for(size_t j=0;j<ne;++j){Doc x;b>>x;}
        auto pt=integers(b);auto joint=c.terms(qt,pt);size_t sources=0;
        auto gates=rank_direct(c,qt,src,joint,sources);
        out<<q<<'\t'<<src<<'\t'<<sources;
        for(const Gate& g:gates) {
            out<<'\t'<<(g.winner==NONE?-1:int64_t(g.winner))<<'\t'<<g.count<<'\t'<<g.begin<<'\t'<<g.end<<'\t'<<g.words<<'\t'<<g.df;
        }
        out<<'\n';++count;
    }
    if(count!=12576||std::getline(inputs,line)||std::getline(seconds,line)||std::getline(seeds,line))throw std::runtime_error("row count mismatch");
    std::cerr<<"Completed "<<count<<" gold-blind address choices per gate\n";
}

