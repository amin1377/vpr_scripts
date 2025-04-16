#include <pugixml.hpp>
#include <iostream>
#include <unordered_set>
#include <string>
#include <vector>
#include <unordered_map>
#include <tuple>
#include <cassert>
#include <cstdlib>
#include <fstream>
#include <numeric>
#include <chrono>
struct AnalyzeNodeInfo {
    std::tuple<int, int, int> low_location;
    std::tuple<int, int, int> high_location;
    std::string type;
    std::vector<int> sink_nodes;
    std::vector<int> source_nodes;
    int direction;
    int length;
};

struct SegmentInfo {
    int segment_id;
    int length;
};

struct AnalyzeRRGraphArgs {
    std::string rr_graph_dir;
};

void dump_to_csv(const std::vector<std::vector<double>>& grid, const std::string& filename) {
    size_t max_x = grid.size();
    size_t max_y = grid.empty() ? 0 : grid[0].size();

    std::ofstream out(filename);
    for (size_t y = 0; y < max_y; ++y) {
        for (size_t x = 0; x < max_x; ++x) {
            out << grid[x][y];
            if (x + 1 < max_x) out << ",";
        }
        out << "\n";
    }
}

// Function to get maximum grid dimensions
std::tuple<int, int, int> get_grid_loc(pugi::xml_node root_tag) {
    pugi::xml_node grid_tag = root_tag.child("grid");
    int max_x = 0;
    int max_y = 0;
    int max_layer = 0;
    
    for (pugi::xml_node grid_loc_tag : grid_tag.children()) {
        int loc_x = std::stoi(grid_loc_tag.attribute("x").value());
        int loc_y = std::stoi(grid_loc_tag.attribute("y").value());
        int loc_layer = std::stoi(grid_loc_tag.attribute("layer").value());
        
        if (loc_x > max_x) max_x = loc_x;
        if (loc_y > max_y) max_y = loc_y;
        if (loc_layer > max_layer) max_layer = loc_layer;
    }
    
    return {max_x, max_y, max_layer};
}

std::unordered_map<int, SegmentInfo> get_segment_info(pugi::xml_node root_tag) {
    pugi::xml_node segments_tag = root_tag.child("segments");
    std::unordered_map<int, SegmentInfo> segments;

    for (pugi::xml_node segment_tag : segments_tag.children()) {
        SegmentInfo seg;
        seg.segment_id = std::stoi(segment_tag.attribute("id").value());
        seg.length = std::stoi(segment_tag.attribute("length").value());
        segments[seg.segment_id] = seg;
    }

    return segments;
}

void analyze_rr_graph(const AnalyzeRRGraphArgs& args) {
    std::string rr_graph_dir = args.rr_graph_dir;
    pugi::xml_document doc;

    std::cout << "Loading RR Graph from " << rr_graph_dir << std::endl;
    std::chrono::steady_clock::time_point start_time = std::chrono::steady_clock::now();
    pugi::xml_parse_result result = doc.load_file(rr_graph_dir.c_str());
    if (!result) {
        std::cerr << "XML parsing error: " << result.description() << std::endl;
        return;
    }
    std::chrono::steady_clock::time_point end_time = std::chrono::steady_clock::now();
    std::cout << "RR Graph loaded successfully in " << std::chrono::duration_cast<std::chrono::seconds>(end_time - start_time).count() << " s" << std::endl;
        
    // Get root element
    pugi::xml_node root = doc.root().first_child();
    pugi::xml_node rr_nodes_tag = root.child("rr_nodes");
    pugi::xml_node rr_edges_tag = root.child("rr_edges");
    
    // Process nodes
    std::unordered_map<int, AnalyzeNodeInfo> nodes;
    auto [max_x, max_y, max_layer] = get_grid_loc(root);
    std::cout << "Grid size: " << max_x << " x " << max_y << " x " << max_layer << std::endl;

    auto segments = get_segment_info(root);
    
    std::cout << "Start initializing axilary data structure..." << std::endl;
    start_time = std::chrono::steady_clock::now();
    for (pugi::xml_node node_tag : rr_nodes_tag.children()) {
        int node_id = node_tag.attribute("id").as_int();
        pugi::xml_node loc_tag = node_tag.child("loc");

        std::tuple<int, int, int> loc_low = {
            std::stoi(loc_tag.attribute("xlow").value()),
            std::stoi(loc_tag.attribute("ylow").value()),
            std::stoi(loc_tag.attribute("layer").value())
        };
        
        std::tuple<int, int, int> loc_high = {
            std::stoi(loc_tag.attribute("xhigh").value()),
            std::stoi(loc_tag.attribute("yhigh").value()),
            std::stoi(loc_tag.attribute("layer").value())
        };
        
        std::string type = node_tag.attribute("type").value();
        
        AnalyzeNodeInfo node;
        node.low_location = loc_low;
        node.high_location = loc_high;
        node.type = type;
        node.length = -1;  // Default value
        node.direction = 0; // Default value

        if (type == "CHANX" || type == "CHANY") {
            std::string node_dir = node_tag.attribute("direction").value();
            pugi::xml_node seg_tag = node_tag.child("segment");
            int seg_id = std::stoi(seg_tag.attribute("segment_id").value());
            if (seg_id == 0) {
                node.length = segments[seg_id].length;
            } else {
                assert(seg_id == 1);
                node.length = segments[seg_id].length;
            }
            if (node_dir == "INC_DIR") {
                node.direction = 1;
            } else if (node_dir == "DEC_DIR") {
                node.direction = -1;
            } else {
                assert(false);
            }
        }
        nodes.insert({node_id, node});
    }

    for (pugi::xml_node edge_tag : rr_edges_tag.children()) {
        int src_node_id = edge_tag.attribute("src").as_int();
        int sink_node_id = edge_tag.attribute("src_node").as_int();
        
        nodes[src_node_id].sink_nodes.push_back(sink_node_id);
        nodes[sink_node_id].source_nodes.push_back(src_node_id);
    }
    end_time = std::chrono::steady_clock::now();
    std::cout << "Axilary data structure initialized successfully in " << std::chrono::duration_cast<std::chrono::seconds>(end_time - start_time).count() << " s" << std::endl;

    std::vector<std::vector<std::vector<int>>> grid_mux_size(max_x, std::vector<std::vector<int>>(max_y, std::vector<int>()));

    for (auto& [node_id, node] : nodes) {
        if (node.type == "CHANX" || node.type == "CHANY") {
            std::tuple<int, int, int> source_loc;
            assert(node.direction == 1 || node.direction == -1);
            if (node.direction == 1) {
                source_loc = node.low_location;
            } else {
                source_loc = node.high_location;
            }
            auto [x, y, layer] = source_loc;
            grid_mux_size[x][y].push_back(static_cast<int>(node.source_nodes.size()));
        }
    }


    std::vector<std::vector<double>> grid_mux_size_avg(max_x, std::vector<double>(max_y, 0));
    for (int x = 0; x < max_x; ++x) {
        for (int y = 0; y < max_y; ++y) {
            if (grid_mux_size[x][y].size() > 0) {
                grid_mux_size_avg[x][y] = std::accumulate(grid_mux_size[x][y].begin(), grid_mux_size[x][y].end(), 0) / static_cast<double>(grid_mux_size[x][y].size());
            }
        }
    }

    double total_mux_avg = 0;
    int total_mux_count = 0;
    for (int x = 3; x < max_x-3; ++x) {
        for (int y = 3; y < max_y-3; ++y) {
            total_mux_avg += std::accumulate(grid_mux_size[x][y].begin(), grid_mux_size[x][y].end(), 0);
            total_mux_count += grid_mux_size[x][y].size();
        }
    }
    total_mux_avg /= static_cast<double>(total_mux_count);

    std::cout << "Total Mux Average: " << total_mux_avg << std::endl;

    dump_to_csv(grid_mux_size_avg, "mux_avg.csv");
}
    

int main(int argc, char** argv) {
    if (argc != 2) {
        std::cerr << "Usage: " << argv[0] << " <rr_graph_dir>" << std::endl;
        return 1;
    }
    AnalyzeRRGraphArgs args;
    args.rr_graph_dir = argv[1];
    analyze_rr_graph(args);
    return 0;
}