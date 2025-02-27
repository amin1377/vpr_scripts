#include "adjust_3d_driver_size.h"

namespace fs = std::filesystem;

// Main function to adjust fan-in/fan-out
void adjust_fan_in_out(const AdjustFanInOutArgs& args) {
    pugi::xml_document& doc = args.doc;
    double mux_removal_rate = args.mux_removal_rate;

    pugi::xml_node root = doc.document_element();
    pugi::xml_node rr_node_tag = root.child("rr_nodes");
    pugi::xml_node rr_edge_tag = root.child("rr_edges");

    std::unordered_map<int, NodeInfo> nodes;
    auto [max_x, max_y, max_layer] = get_grid_loc(root);
    
    // Initialize nodes data structure
    for (pugi::xml_node node_tag : rr_node_tag.children()) {
        int node_id = std::stoi(node_tag.attribute("id").value());
        pugi::xml_node loc_tag = node_tag.child("loc");
        std::tuple<int, int, int> loc_high = {
            std::stoi(loc_tag.attribute("xhigh").value()),
            std::stoi(loc_tag.attribute("yhigh").value()),
            std::stoi(loc_tag.attribute("layer").value())
        };
        
        nodes[node_id].high_location = loc_high;
    }

    // Initialize 3D grid for edges
    std::vector<std::vector<std::vector<std::vector<pugi::xml_node>>>> grid_3d_edge_tag(
        max_layer + 1,
        std::vector<std::vector<std::vector<pugi::xml_node>>>(
            max_x + 1,
            std::vector<std::vector<pugi::xml_node>>(
                max_y + 1
            )
        )
    );

    std::unordered_set<int> nodes_under_consideration;
    std::vector<pugi::xml_node> original_edges;

    // Populate original edges and identify nodes under consideration
    for (pugi::xml_node edge_tag : rr_edge_tag.children()) {
        int src_node = std::stoi(edge_tag.attribute("src_node").value());
        int sink_node = std::stoi(edge_tag.attribute("sink_node").value());
        original_edges.push_back(edge_tag);

        int src_x = std::get<0>(nodes[src_node].high_location);
        int src_y = std::get<1>(nodes[src_node].high_location);
        int src_layer = std::get<2>(nodes[src_node].high_location);

        int sink_layer = std::get<2>(nodes[sink_node].high_location);
        
        if (src_layer != sink_layer) {
            nodes_under_consideration.insert(src_node);
            nodes_under_consideration.insert(sink_node);
            grid_3d_edge_tag[src_layer][src_x][src_y].push_back(edge_tag);
        }
    }

    // Populate in/out edges for nodes under consideration
    for (pugi::xml_node edge_tag : rr_edge_tag.children()) {
        int src_node = std::stoi(edge_tag.attribute("src_node").value());
        int sink_node = std::stoi(edge_tag.attribute("sink_node").value());
        
        if (nodes_under_consideration.find(src_node) != nodes_under_consideration.end() || 
            nodes_under_consideration.find(sink_node) != nodes_under_consideration.end()) {
            nodes[src_node].out_edges.push_back(edge_tag);
            nodes[sink_node].in_edges.push_back(edge_tag);
        }
    }
              
    // Random number generator
    std::random_device rd;
    std::mt19937 gen(rd());

    // Process each mux removal rate
    std::vector<pugi::xml_node> edges_to_remove;
    
    // Identify edges to remove
    for (int l = 0; l <= max_layer; l++) {
        for (int x = 0; x <= max_x; x++) {
            for (int y = 0; y <= max_y; y++) {
                for (pugi::xml_node edge_tag : grid_3d_edge_tag[l][x][y]) {
                    int src_node = std::stoi(edge_tag.attribute("src_node").value());
                    int sink_node = std::stoi(edge_tag.attribute("sink_node").value());

                    std::vector<pugi::xml_node>& fan_in_edges = nodes[src_node].in_edges;
                    std::vector<pugi::xml_node>& fan_out_edges = nodes[sink_node].out_edges;
                    
                    // Random sampling for fan-in edges
                    int num_elem = static_cast<int>(fan_in_edges.size() * mux_removal_rate);
                    if (num_elem > 0 && !fan_in_edges.empty()) {
                        std::shuffle(fan_in_edges.begin(), fan_in_edges.end(), gen);
                        edges_to_remove.insert(edges_to_remove.end(), 
                                                fan_in_edges.begin(), 
                                                fan_in_edges.begin() + std::min(num_elem, static_cast<int>(fan_in_edges.size())));
                    }
                    
                    // Random sampling for fan-out edges
                    num_elem = static_cast<int>(fan_out_edges.size() * mux_removal_rate);
                    if (num_elem > 0 && !fan_out_edges.empty()) {
                        std::shuffle(fan_out_edges.begin(), fan_out_edges.end(), gen);
                        edges_to_remove.insert(edges_to_remove.end(), 
                                                fan_out_edges.begin(), 
                                                fan_out_edges.begin() + std::min(num_elem, static_cast<int>(fan_out_edges.size())));
                    }
                }
            }
        }
    }

    for (pugi::xml_node edge : edges_to_remove) {
        rr_edge_tag.remove_child(edge);
    }
}