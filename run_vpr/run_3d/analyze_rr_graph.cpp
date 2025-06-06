#include <iostream>
#include <unordered_set>
#include <string>
#include <vector>
#include <unordered_map>
#include <tuple>
#include <cassert>
#include <cstdlib>
#include <fstream>

#include "pugixml.hpp"
#include "analyze_rr_graph.h"
#include "common_util.h"

struct AnalyzeNodeInfo {
    std::tuple<int, int, int> high_location;
    std::string type;
    std::vector<int> sink_nodes;
    std::vector<int> source_nodes;
    int length;
};

void analyze_rr_graph(const AnalyzeRRGraphArgs& args) {
    std::string rr_graph_dir = args.rr_graph_dir;
    pugi::xml_document doc;

    pugi::xml_parse_result result = doc.load_file(rr_graph_dir.c_str());
    if (!result) {
        std::cerr << "XML parsing error: " << result.description() << std::endl;
        return;
    }

    std::string output_file_name = "rr_graph_analysis.rpt";
    std::ofstream output_file(output_file_name);
    if (!output_file) {
        std::cerr << "Failed to open output file." << std::endl;
        return;
    }
        
    // Get root element
    pugi::xml_node root = doc.root().first_child();
    pugi::xml_node rr_nodes_tag = root.child("rr_nodes");
    pugi::xml_node rr_edges_tag = root.child("rr_edges");
    
    // Process nodes
    std::unordered_map<int, AnalyzeNodeInfo> nodes;
    auto [max_x, max_y, max_layer] = get_grid_loc(root);
    
    for (pugi::xml_node node_tag : rr_nodes_tag.children()) {
        int node_id = node_tag.attribute("id").as_int();
        pugi::xml_node loc_tag = node_tag.child("loc");
        
        std::tuple<int, int, int> loc_high = {
            std::stoi(loc_tag.attribute("xhigh").value()),
            std::stoi(loc_tag.attribute("yhigh").value()),
            std::stoi(loc_tag.attribute("layer").value())
        };
        
        std::string type = node_tag.attribute("type").value();
        
        AnalyzeNodeInfo node;
        node.high_location = loc_high;
        node.type = type;
        node.length = -1;  // Default value
        
        if (type == "CHANX" || type == "CHANY") {
            pugi::xml_node seg_tag = node_tag.child("segment");
            int seg_id = std::stoi(seg_tag.attribute("segment_id").value());
            if (seg_id == 0) {
                node.length = 4;
            } else {
                assert(seg_id == 1);
                node.length = 16;
            }
        }
        nodes.insert({node_id, node});
    }

    std::unordered_set<int> node_under_consideration;
    for (pugi::xml_node edge_tag : rr_edges_tag.children()) {
        int src_node = edge_tag.attribute("src_node").as_int();
        int sink_node = edge_tag.attribute("sink_node").as_int();
        int src_layer = std::get<2>(nodes[src_node].high_location);
        int sink_layer = std::get<2>(nodes[sink_node].high_location);
        if (src_layer != sink_layer) {
            node_under_consideration.insert(src_node);
            node_under_consideration.insert(sink_node);
        }
    }

    // Process edges
    for (pugi::xml_node edge_tag : rr_edges_tag.children()) {
        int src_node = edge_tag.attribute("src_node").as_int();
        int sink_node = edge_tag.attribute("sink_node").as_int();
        
        if (node_under_consideration.find(src_node) != node_under_consideration.end()) {
            nodes[src_node].sink_nodes.push_back(sink_node);
        }
        if (node_under_consideration.find(sink_node) != node_under_consideration.end()) {
            nodes[sink_node].source_nodes.push_back(src_node);
        }
    }
    

    // Initialize grid structures
    std::vector<std::vector<std::vector<int>>> grid(max_layer + 1, 
        std::vector<std::vector<int>>(max_x + 1, 
            std::vector<int>(max_y + 1, 0)));
    
    
    struct MuxStats {
        int total = 0;
        int l4 = 0;
        int l16 = 0;
    };
    
    std::vector<std::vector<std::vector<MuxStats>>> mux_fan_in(max_layer + 1, 
        std::vector<std::vector<MuxStats>>(max_x + 1, 
            std::vector<MuxStats>(max_y + 1)));
            
    std::vector<std::vector<std::vector<MuxStats>>> mux_fan_out(max_layer + 1, 
        std::vector<std::vector<MuxStats>>(max_x + 1, 
            std::vector<MuxStats>(max_y + 1)));
    
    // Process inter-die connections
    for (pugi::xml_node edge_tag : rr_edges_tag.children()) {
        int src_node = edge_tag.attribute("src_node").as_int();
        int sink_node = edge_tag.attribute("sink_node").as_int();
        
        int src_x = std::get<0>(nodes[src_node].high_location);
        int src_y = std::get<1>(nodes[src_node].high_location);
        int src_layer = std::get<2>(nodes[src_node].high_location);
        
        int sink_layer = std::get<2>(nodes[sink_node].high_location);
        
        if (src_layer != sink_layer) {
            grid[src_layer][src_x][src_y]++;
            
            int num_l4_source = 0;
            int num_l16_source = 0;
            for (int parent_source : nodes[src_node].source_nodes) {
                std::string node_type = nodes[parent_source].type;
                assert(node_type == "CHANX" || node_type == "CHANY");
                int chan_len = nodes[parent_source].length;
                if (chan_len == 4) {
                    num_l4_source++;
                } else {
                    assert(chan_len == 16);
                    num_l16_source++;
                }
            }
            
            int num_l4_sink = 0;
            int num_l16_sink = 0;
            for (int parent_sink : nodes[sink_node].sink_nodes) {
                std::string node_type = nodes[parent_sink].type;
                assert(node_type == "CHANX" || node_type == "CHANY");
                int chan_len = nodes[parent_sink].length;
                if (chan_len == 4) {
                    num_l4_sink++;
                } else {
                    assert(chan_len == 16);
                    num_l16_sink++;
                }
            }
            
            int fan_in = nodes[src_node].source_nodes.size();
            int fan_out = nodes[sink_node].sink_nodes.size();
            
            mux_fan_in[src_layer][src_x][src_y].total += fan_in;
            mux_fan_in[src_layer][src_x][src_y].l4 += num_l4_source;
            mux_fan_in[src_layer][src_x][src_y].l16 += num_l16_source;
            
            mux_fan_out[src_layer][src_x][src_y].total += fan_out;
            mux_fan_out[src_layer][src_x][src_y].l4 += num_l4_sink;
            mux_fan_out[src_layer][src_x][src_y].l16 += num_l16_sink;
            
            // output_file << "(" << src_node << "->" << sink_node << "): "
            //           << "Fan-in: " << fan_in 
            //           << " (L4: " << num_l4_source 
            //           << ", L16: " << num_l16_source 
            //           << ") Fan-out: " << fan_out 
            //           << " (L4: " << num_l4_sink 
            //           << ", L16: " << num_l16_sink << ")" << std::endl;
        }
    }
    
    // Calculate totals and averages
    std::vector<int> total_fan_in(2, 0);
    std::vector<int> total_fan_out(2, 0);
    
    for (int x = 0; x <= max_x; x++) {
        for (int y = 0; y <= max_y; y++) {
            if (x != 0 && y != 0) {  // Skip (0,0)
                for (int l = 0; l <= max_layer; l++) {
                    if (grid[l][x][y] > 0) {  // Avoid division by zero
                        total_fan_in[l] += mux_fan_in[l][x][y].total;
                        total_fan_out[l] += mux_fan_out[l][x][y].total;
                        
                        mux_fan_in[l][x][y].total /= grid[l][x][y];
                        mux_fan_in[l][x][y].l4 /= grid[l][x][y];
                        mux_fan_in[l][x][y].l16 /= grid[l][x][y];
                        
                        mux_fan_out[l][x][y].total /= grid[l][x][y];
                        mux_fan_out[l][x][y].l4 /= grid[l][x][y];
                        mux_fan_out[l][x][y].l16 /= grid[l][x][y];
                    }
                }
            }
        }
    }

    
    // Print statistics
    std::vector<int> acc(2, 0);
    std::vector<int> num(2, 0);
    
    for (int x = 0; x <= max_x; x++) {
        for (int y = 0; y <= max_y; y++) {
            if (x != 0 && y != 0) {  // Skip (0,0)
                for (int l = 0; l <= max_layer; l++) {
                    acc[l] += grid[l][x][y];
                    num[l]++;
                    
                    output_file << x << " " << y << " " << l << std::endl;
                    output_file << "\t Number of inter-die connections: " << grid[l][x][y] << std::endl;
                    output_file << "\t Average inter-die edge fan-in: " << mux_fan_in[l][x][y].total
                              << " (l4: " << mux_fan_in[l][x][y].l4
                              << " l16: " << mux_fan_in[l][x][y].l16 << ")" << std::endl;
                    output_file << "\t Average inter-die edge fan-out: " << mux_fan_out[l][x][y].total
                              << " (l4: " << mux_fan_out[l][x][y].l4
                              << " l16: " << mux_fan_out[l][x][y].l16 << ")" << std::endl;
                }
            }
        }
    }
    
    // Print overall averages
    if (num[0] > 0 && num[1] > 0) {
        output_file << "Average number of inter-die connections per tile: "
                  << "0->1: " << static_cast<float>(acc[0]) / num[0] << " - "
                  << "1->0: " << static_cast<float>(acc[1]) / num[1] << std::endl;
    }
    
    if (acc[0] > 0 && acc[1] > 0) {
        output_file << "Average fan-in and fan-out per inter-die connection: "
                  << "0: Fan-in " << static_cast<float>(total_fan_in[0]) / acc[0]
                  << ", Fan-out " << static_cast<float>(total_fan_out[0]) / acc[0]
                  << " - 1: Fan-in " << static_cast<float>(total_fan_in[1]) / acc[1]
                  << ", Fan-out " << static_cast<float>(total_fan_out[1]) / acc[1] << std::endl;
    }

    output_file.close();
}