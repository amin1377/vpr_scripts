#ifndef REMOVE_INTER_DIE_CONNECTION_H
#define REMOVE_INTER_DIE_CONNECTION_H

#include <tuple>
#include <vector>
#include <string>
#include "pugixml.hpp"
#include "graph.h"
#include "common_util.h"

struct RemoveInterDieConnectionArgs {
    pugi::xml_document& doc;
    double edge_removal_rate;
};

GridLoc get_grid_loc(pugi::xml_node root_tag) {
    GridLoc result = {0, 0, 0};
    
    pugi::xml_node grid_tag = root_tag.child("grid");
    
    for (pugi::xml_node grid_loc_tag : grid_tag.children()) {
        int loc_x = grid_loc_tag.attribute("x").as_int();
        int loc_y = grid_loc_tag.attribute("y").as_int();
        int loc_layer = grid_loc_tag.attribute("layer").as_int();
        
        if (loc_x > result.max_x) {
            result.max_x = loc_x;
        }
        if (loc_y > result.max_y) {
            result.max_y = loc_y;
        }
        if (loc_layer > result.max_layer) {
            result.max_layer = loc_layer;
        }
    }
    
    return result;
}

void remove_inter_die_edge(const RemoveInterDieConnectionArgs& args);

#endif