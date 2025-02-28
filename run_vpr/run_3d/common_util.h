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

    GridLoc(int max_x, int max_y, int max_layer) : max_x(max_x), max_y(max_y), max_layer(max_layer) {}
    GridLoc(std::tuple<int, int, int> loc) : max_x(std::get<0>(loc)), max_y(std::get<1>(loc)), max_layer(std::get<2>(loc)) {}
};

struct NodeInfo {
    std::tuple<int, int, int> high_location;
    std::vector<pugi::xml_node> out_edges;
    std::vector<pugi::xml_node> in_edges;
};

std::tuple<int, int, int> get_grid_loc(pugi::xml_node root_tag);

double getPeakMemoryUsageMB();
double getCurrentMemoryUsageMB();

#endif