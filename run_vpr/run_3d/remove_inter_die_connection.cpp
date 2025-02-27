#include <unordered_map>
#include <random>
#include <iostream>
#include "remove_inter_die_connection.h"


void remove_inter_die_edge(const RemoveInterDieConnectionArgs& args) {
    pugi::xml_document& doc = args.doc;
    double edge_removal_rate = args.edge_removal_rate;

    pugi::xml_node root = doc.root().first_child();
    pugi::xml_node rr_node_tag = root.child("rr_nodes");
    pugi::xml_node rr_edge_tag = root.child("rr_edges");

    std::unordered_map<int, NodeInfo> nodes;

    GridLoc grid_loc = get_grid_loc(root);

    for (pugi::xml_node node_tag : rr_node_tag.children()) {
        int node_id = node_tag.attribute("id").as_int();
        pugi::xml_node loc_tag = node_tag.child("loc");
        
        std::tuple<int, int, int> loc_high(
            loc_tag.attribute("xhigh").as_int(),
            loc_tag.attribute("yhigh").as_int(),
            loc_tag.attribute("layer").as_int()
        );
                
        nodes[node_id] = {loc_high};
    }

    // 3D grid to store edges between different layers
    std::vector<std::vector<std::vector<std::vector<pugi::xml_node>>>> grid_3d_edge_tag;
    
    grid_3d_edge_tag.resize(grid_loc.max_layer + 1);
    for (int l = 0; l <= grid_loc.max_layer; l++) {
        grid_3d_edge_tag[l].resize(grid_loc.max_x + 1);
        for (int x = 0; x <= grid_loc.max_x; x++) {
            grid_3d_edge_tag[l][x].resize(grid_loc.max_y + 1);
        }
    }

    for (pugi::xml_node edge_tag : rr_edge_tag.children()) {
        int src_node = edge_tag.attribute("src_node").as_int();
        int sink_node = edge_tag.attribute("sink_node").as_int();
        
        int src_x = std::get<0>(nodes[src_node].high_location);
        int src_y = std::get<1>(nodes[src_node].high_location);
        int src_layer = std::get<2>(nodes[src_node].high_location);

        int sink_layer = std::get<2>(nodes[sink_node].high_location);
        
        if (src_layer != sink_layer) {
            grid_3d_edge_tag[src_layer][src_x][src_y].push_back(edge_tag);
        }
    }

    std::vector<pugi::xml_node> edges_to_remove;
    std::mt19937 gen(std::random_device{}());
    
    for (int x = 0; x <= grid_loc.max_x; x++) {
        for (int y = 0; y <= grid_loc.max_y; y++) {
            for (int l = 0; l <= grid_loc.max_layer; l++) {
                auto& edges = grid_3d_edge_tag[l][x][y];
                int num_elem = static_cast<int>(edges.size() * edge_removal_rate);
                
                if (num_elem > 0 && !edges.empty()) {
                    std::vector<int> indices(edges.size());
                    for (size_t i = 0; i < indices.size(); i++) {
                        indices[i] = i;
                    }
                    
                    std::shuffle(indices.begin(), indices.end(), gen);
                    
                    for (int i = 0; i < num_elem && i < indices.size(); i++) {
                        edges_to_remove.push_back(edges[indices[i]]);
                    }
                }
            }
        }
    }

    for (pugi::xml_node edge : edges_to_remove) {
        rr_edge_tag.remove_child(edge);
    }
}