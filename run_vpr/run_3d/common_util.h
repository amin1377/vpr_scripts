#ifndef COMMON_UTIL_H
#define COMMON_UTIL_H

#include <tuple>
#include <vector>
#include <string>
#include "pugixml.hpp"

struct GridLoc {
    int max_x;
    int max_y;
    int max_layer;
};

struct NodeInfo {
    std::tuple<int, int, int> high_location;
    std::vector<pugi::xml_node> out_edges;
    std::vector<pugi::xml_node> in_edges;
};

std::tuple<int, int, int> get_grid_loc(pugi::xml_node root_tag);

#endif