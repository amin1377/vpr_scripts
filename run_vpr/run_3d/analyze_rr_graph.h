#ifndef ANALYZE_RR_GRAPH_H
#define ANALYZE_RR_GRAPH_H

#include "pugixml.hpp"

struct AnalyzeRRGraphArgs {
    std::string rr_graph_dir;
};

void analyze_rr_graph(const AnalyzeRRGraphArgs& args);

#endif
