#define main native_retrieval_main
#include "../global_titles/retrieval.cpp"
#undef main
int main(){
    Corpus c;std::ifstream in("candidate.in");std::ofstream out("candidate-seeds.tsv");std::string line;
    while(std::getline(in,line)){
        std::istringstream r(line);std::string q;r>>q;auto tokens=integers(r);auto terms=c.terms(tokens);
        auto matches=c.phrases(tokens,NONE);
        Doc chosen=matches.empty()?c.global(terms,NONE):c.local(matches,terms);
        out<<q<<'\t'<<chosen<<'\t'<<c.page[chosen]<<'\t'<<matches.size()<<'\n';
    }
}

