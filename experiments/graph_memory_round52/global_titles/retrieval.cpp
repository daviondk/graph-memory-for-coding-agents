// Exact BM25 and whole-title enumeration over the authors' directory. No approximate neighbors.
#include <algorithm>
#include <cassert>
#include <cmath>
#include <cstdint>
#include <fstream>
#include <iostream>
#include <limits>
#include <sstream>
#include <stdexcept>
#include <string>
#include <unordered_map>
#include <utility>
#include <vector>
using Doc = uint32_t;
using Word = uint32_t;
constexpr Doc NONE = std::numeric_limits<Doc>::max();
template<class T> T number(std::istream& in) {
    T v; if (!in.read(reinterpret_cast<char*>(&v),sizeof(v))) throw std::runtime_error("truncated input");
    return v;
}
struct Posting { Doc row; uint16_t frequency; };
struct Trienode { Doc head=NONE; };
struct Terms { std::vector<Word> words; std::vector<double> weights; };
struct Corpus {
    std::vector<unsigned char> stop;
    std::vector<uint32_t> page, start, flat, next;
    std::vector<uint16_t> length;
    std::vector<double> norm,idf, accum;
    std::vector<uint32_t> stamp;
    std::vector<std::vector<Posting>> lists;
    std::unordered_map<uint64_t,uint32_t> children;
    std::vector<Trienode> trie{Trienode{}};
    Doc tie_low=NONE; uint32_t epoch=0;
    Corpus() {
        std::ifstream st("stop.bin",std::ios::binary);
        stop.assign(std::istreambuf_iterator<char>(st),{});
        if(stop.empty()) throw std::runtime_error("missing stop mask");
        lists.resize(stop.size()); children.reserve(10000000);trie.reserve(9500000);
        std::ifstream f("lex.bin",std::ios::binary);
        if(!f) throw std::runtime_error("missing title corpus");
        uint64_t total=0;std::vector<Word> words,terms;
        while(f.peek()!=EOF) {
            auto id=number<uint32_t>(f); auto n=number<uint16_t>(f);auto admissible=number<uint16_t>(f);
            words.resize(n);if(!f.read(reinterpret_cast<char*>(words.data()),4*n)) throw std::runtime_error("truncated title");
            Doc row=page.size();page.push_back(id);next.push_back(NONE);start.push_back(flat.size());
            if(tie_low==NONE||id<page[tie_low])tie_low=row;
            uint32_t node=0;terms.clear();
            for(Word w:words) {
                if(!stop.at(w))terms.push_back(w);
                if(admissible) {
                    uint64_t address=(uint64_t(node)<<32)|w;
                    auto [it,inserted]=children.try_emplace(address,trie.size());
                    if(inserted)trie.emplace_back();
                    node=it->second;
                }
            }
            if(admissible){next[row]=trie[node].head;trie[node].head=row;}
            std::sort(terms.begin(),terms.end());flat.insert(flat.end(),terms.begin(),terms.end());
            total+=terms.size();length.push_back(terms.size());
            for(size_t i=0,j;i<terms.size();i=j) {
                j=i+1;while(j<terms.size()&&terms[j]==terms[i])++j;
                lists[terms[i]].push_back({row,static_cast<uint16_t>(j-i)});
            }
        }
        start.push_back(flat.size());
        if(page.size()!=5989847) throw std::runtime_error("unexpected record count");
        double avg=double(total)/page.size();
        for(auto len:length) norm.push_back(1.2*(0.25+0.75*len/avg));
        for(const auto& list:lists)idf.push_back(std::log1p((page.size()-list.size()+0.5)/(list.size()+0.5)));
        accum.resize(page.size());stamp.resize(page.size());
    }
    bool better(Doc x,Doc y) const {return y==NONE || page[x]<page[y] || (page[x]==page[y]&&x<y);}
    std::vector<Doc> phrases(const std::vector<Word>& sequence,Doc excluded) const {
        std::vector<Doc> hits;
        for(size_t a=0;a<sequence.size();++a) {
            uint32_t node=0;
            for(size_t b=a;b<sequence.size();++b) {
                auto it=children.find((uint64_t(node)<<32)|sequence[b]);if(it==children.end())break;
                node=it->second;
                for(Doc d=trie[node].head;d!=NONE;d=next[d])if(d!=excluded)hits.push_back(d);
            }
        }
        std::sort(hits.begin(),hits.end());hits.erase(std::unique(hits.begin(),hits.end()),hits.end());return hits;
    }
    Terms terms(std::vector<Word> q,std::vector<Word> p={}) const {
        auto unique=[](auto& v){std::sort(v.begin(),v.end());v.erase(std::unique(v.begin(),v.end()),v.end());};
        unique(q);unique(p);
        Terms t;std::set_union(q.begin(),q.end(),p.begin(),p.end(),std::back_inserter(t.words));
        t.words.erase(std::remove_if(t.words.begin(),t.words.end(),[&](Word w){return stop.at(w);}),t.words.end());
        for(auto w:t.words)t.weights.push_back(idf[w]*((std::binary_search(q.begin(),q.end(),w)?1.:0.)+
                                                    (std::binary_search(p.begin(),p.end(),w)?.25:0.)));
        return t;
    }
    double contribution(Doc d,double weight,int tf) const {return weight*(2.2*tf/(tf+norm[d]));}
    double score(Doc d,const Terms& t) const {
        double sum=0; uint32_t i=start[d],end=start[d+1];
        while(i<end){
            Word w=flat[i];uint32_t j=i+1;while(j<end && flat[j]==w)++j;
            auto it=std::lower_bound(t.words.begin(),t.words.end(),w);
            if(it!=t.words.end()&&*it==w)sum+=contribution(d,t.weights[it-t.words.begin()],j-i);
            i=j;
        }
        return sum;
    }
    Doc local(const std::vector<Doc>& candidates,const Terms& t) const {
        Doc winner=NONE;double best=-1;
        for(Doc d:candidates){double v=score(d,t);if(v>best||(v==best&&better(d,winner))){winner=d;best=v;}}
        return winner;
    }
    Doc global(const Terms& t,Doc excluded){
        ++epoch;std::vector<Doc> touched;
        for(size_t i=0;i<t.words.size();++i){
            for(auto e:lists[t.words[i]]){
                if(stamp[e.row]!=epoch){stamp[e.row]=epoch;accum[e.row]=0;touched.push_back(e.row);}
                accum[e.row]+=contribution(e.row,t.weights[i],e.frequency);
            }
        }
        Doc winner=NONE;double best=-1;
        for(auto d:touched){if(d==excluded)continue;double v=accum[d];if(v>best||(v==best&&better(d,winner))){winner=d;best=v;}}
        if(winner==NONE){winner=tie_low;if(winner==excluded){winner=NONE;for(Doc j=0;j<page.size();++j)if(j!=excluded&&better(j,winner))winner=j;}}
        if(best>0 && accum[winner]!=score(winner,t))throw std::runtime_error("BM25 summation disagreement");
        return winner;
    }
};
std::vector<Doc> intersect(const std::vector<Doc>& a,const std::vector<Doc>& b){
    std::vector<Doc> v;std::set_intersection(a.begin(),a.end(),b.begin(),b.end(),std::back_inserter(v));return v;
}
std::vector<unsigned> integers(std::istringstream& in){
    std::vector<unsigned> result;unsigned x;while(in>>x)result.push_back(x);return result;
}
int main(int argc,char** argv){
    if(argc!=2){std::cerr<<"seed or second\n";return 1;}const std::string stage=argv[1];if(stage!="seed"&&stage!="second")return 1;
    Corpus c; std::ifstream input("questions.in"),extra("second.in");std::ofstream out(stage+".tsv");
    std::string line;size_t count=0;
    while(std::getline(input,line)){
        std::istringstream qin(line);std::string q;qin>>q;auto qt=integers(qin);auto one=c.terms(qt);
        if(stage=="seed"){
            auto explicit_q=c.phrases(qt,NONE);auto plain=c.global(one,NONE);
            auto seed=explicit_q.empty()?plain:c.local(explicit_q,one);
            out<<q<<'\t'<<seed<<'\t'<<c.page[seed]<<'\t'<<plain<<'\t'<<explicit_q.size()<<'\n';
        }else{
            std::string eline;if(!std::getline(extra,eline))return 2;std::istringstream ein(eline);
            std::string id;Doc seed;size_t ne;ein>>id>>seed>>ne;if(id!=q)return 3;
            std::vector<Doc> links(ne);for(auto& d:links){ein>>d;if(d==seed||d>=c.page.size())return 4;}
            auto pt=integers(ein);auto joint=c.terms(qt,pt);auto explicit_q=c.phrases(qt,seed);
            auto literal=c.phrases(pt,seed);std::sort(links.begin(),links.end());
            std::vector<Doc> both;std::set_union(links.begin(),links.end(),literal.begin(),literal.end(),std::back_inserter(both));
            Doc base=explicit_q.empty()?c.global(joint,seed):c.local(explicit_q,joint);
            auto choose=[&](const std::vector<Doc>& v){
                if(!explicit_q.empty()){auto in=intersect(v,explicit_q);return in.empty()?base:c.local(in,joint);}
                return v.empty()?base:c.local(v,joint);
            };
            Doc raw=c.global(one,seed),text=choose(literal),href=choose(links),combined=choose(both);
            out<<q<<'\t'<<seed<<'\t'<<base<<'\t'<<raw<<'\t'<<text<<'\t'<<href<<'\t'<<combined<<'\t'
               <<(literal.empty()?base:c.local(literal,joint))<<'\t'<<(links.empty()?base:c.local(links,joint))
               <<'\t'<<explicit_q.size()<<'\t'<<literal.size()<<'\t'<<links.size()<<'\t'<<intersect(literal,links).size()<<'\n';
        }
        ++count;if(count%1000==0)std::cerr<<stage<<' '<<count<<'\n';
    }
    if(count!=12576) return 5;
}

