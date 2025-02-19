#include <iostream>
#include <fstream>
#include <vector>
#include <unordered_map>
#include <unordered_set>
#include <set>
#include <string>
#include <algorithm>
#include <random>
#include <chrono>
#include <filesystem>
#include <thread>
#include <future>
#include <cstdlib>
#include <ctime>
#include <tuple>
#include <pugixml.hpp>

namespace fs = std::filesystem;

// Custom comparator for xml_node
struct EdgeNodeCompare {
    bool operator()(const pugi::xml_node& a, const pugi::xml_node& b) const {
        // Compare by src_node and sink_node attributes
        int a_src = std::stoi(a.attribute("src_node").value());
        int a_sink = std::stoi(a.attribute("sink_node").value());
        int b_src = std::stoi(b.attribute("src_node").value());
        int b_sink = std::stoi(b.attribute("sink_node").value());
        
        if (a_src != b_src) return a_src < b_src;
        return a_sink < b_sink;
    }
};

// Struct to represent a node in the RR graph
struct Node {
    std::tuple<int, int, int> high_location;
    std::vector<pugi::xml_node> out_edges;
    std::vector<pugi::xml_node> in_edges;
};

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

// Check if the RR graph already exists
bool does_rr_graph_exist(const std::string& output_dir, const std::string& circuit, 
                         double edge_removal_rate, double mux_removal_rate) {
    std::string rr_graph_name = "rr_graph_" + circuit + "_" + 
                                std::to_string(static_cast<int>(edge_removal_rate * 100)) + 
                                "_mux_" + std::to_string(static_cast<int>(mux_removal_rate * 100)) + ".xml";
    std::string rr_graph_path = output_dir + "/" + rr_graph_name;
    return fs::exists(rr_graph_path);
}

// Main function to adjust fan-in/fan-out
void adjust_fan_in_out(const std::vector<std::string>& thread_arg) {
    std::string rr_graph_file_dir = thread_arg[0];
    std::string circuit = thread_arg[1];
    double edge_removal_rate = std::stod(thread_arg[2]);
    std::string output_dir = thread_arg[3];

    std::vector<double> mux_removal_rates = {0.05, 0.10, 0.30, 0.50, 0.65, 0.80, 0.90, 0.95, 0.98};

    std::string original_rr_graph_name = "rr_graph_" + circuit + "_" + 
                                     std::to_string(static_cast<int>(edge_removal_rate * 100)) + ".xml";

    std::cout << "Start working on " << original_rr_graph_name << "..." << std::endl;

    auto start_time = std::chrono::high_resolution_clock::now();
    
    // Load XML document
    pugi::xml_document doc;
    pugi::xml_parse_result result = doc.load_file(rr_graph_file_dir.c_str());
    if (!result) {
        std::cerr << "XML parsing failed: " << result.description() << std::endl;
        return;
    }
    
    auto end_time = std::chrono::high_resolution_clock::now();
    std::chrono::duration<double> execution_time = end_time - start_time;
    std::cout << "\tParsing " << original_rr_graph_name << " is done (" 
              << execution_time.count() << " seconds)!" << std::endl;

    pugi::xml_node root = doc.document_element();
    pugi::xml_node rr_node_tag = root.child("rr_nodes");
    pugi::xml_node rr_edge_tag = root.child("rr_edges");

    std::unordered_map<int, Node> nodes;
    auto [max_x, max_y, max_layer] = get_grid_loc(root);

    std::cout << "\tStart initializing auxiliary data structure for " << original_rr_graph_name << ".." << std::endl;
    start_time = std::chrono::high_resolution_clock::now();
    
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

    end_time = std::chrono::high_resolution_clock::now();
    execution_time = end_time - start_time;
    std::cout << "\tDone initializing auxiliary data structure for " << original_rr_graph_name 
              << " (" << execution_time.count() << " seconds)!" << std::endl;

    std::cout << "Original number of edges for " << original_rr_graph_name << ": " 
              << original_edges.size() << std::endl;
              
    // Random number generator
    std::random_device rd;
    std::mt19937 gen(rd());

    // Process each mux removal rate
    for (double mux_removal_rate : mux_removal_rates) {
        std::string rr_graph_name = "rr_graph_" + circuit + "_" + 
                                std::to_string(static_cast<int>(edge_removal_rate * 100)) + 
                                "_mux_" + std::to_string(static_cast<int>(mux_removal_rate * 100)) + ".xml";
        
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

        std::cout << "\tStart removing " << edges_to_remove.size() << " number of edges from " 
                  << rr_graph_name << "..." << std::endl;
        start_time = std::chrono::high_resolution_clock::now();
        
        // Use set instead of unordered_set for xml_node objects
        std::set<pugi::xml_node, EdgeNodeCompare> set_edges_to_remove;
        for (const auto& edge : edges_to_remove) {
            set_edges_to_remove.insert(edge);
        }
        
        // Filter edges to keep
        std::vector<pugi::xml_node> remaining_edges;
        for (pugi::xml_node edge : original_edges) {
            if (set_edges_to_remove.find(edge) == set_edges_to_remove.end()) {
                remaining_edges.push_back(edge);
            }
        }
        
        // Remove all edges
        for (pugi::xml_node child = rr_edge_tag.first_child(); child; ) {
            pugi::xml_node next = child.next_sibling();
            rr_edge_tag.remove_child(child);
            child = next;
        }
        
        // Add back remaining edges
        for (pugi::xml_node edge : remaining_edges) {
            rr_edge_tag.append_copy(edge);
        }
        
        end_time = std::chrono::high_resolution_clock::now();
        execution_time = end_time - start_time;
        std::cout << "\tDone removing " << edges_to_remove.size() << " number of edges from " 
                  << rr_graph_name << " (" << execution_time.count() << " seconds) - " 
                  << remaining_edges.size() << " edges remaining!" << std::endl;
                  
        std::cout << "\tStart writing " << rr_graph_name << std::endl;
        start_time = std::chrono::high_resolution_clock::now();
        
        // Ensure output directory exists
        fs::create_directories(output_dir);
        
        // Write modified XML
        std::string output_path = output_dir + "/" + rr_graph_name;
        bool save_result = doc.save_file(output_path.c_str());
        if (!save_result) {
            std::cerr << "Failed to save XML file: " << output_path << std::endl;
        }
        
        end_time = std::chrono::high_resolution_clock::now();
        execution_time = end_time - start_time;
        std::cout << "\tDone writing " << rr_graph_name << " (" << execution_time.count() << " seconds)!" << std::endl;

        std::cout << "Writing " << rr_graph_name << " is complete!" << std::endl;
    }
}

// Parse command line arguments
std::tuple<std::string, int> getArgs(int argc, char* argv[]) {
    std::string resource_dir;
    int num_threads = 1;
    
    for (int i = 1; i < argc; i++) {
        std::string arg = argv[i];
        if (arg == "--resource_dir" && i + 1 < argc) {
            resource_dir = argv[++i];
        } else if (arg == "-j" && i + 1 < argc) {
            num_threads = std::stoi(argv[++i]);
        }
    }
    
    if (resource_dir.empty()) {
        std::cerr << "Usage: " << argv[0] << " --resource_dir <dir> -j <num_threads>" << std::endl;
        exit(1);
    }
    
    return {resource_dir, num_threads};
}

int main(int argc, char* argv[]) {
    auto [resource_dir, number_of_threads] = getArgs(argc, argv);
    
    // Get list of circuit directories
    std::vector<std::string> circuits = {"gsm_switch_stratixiv_arch_timing", "mes_noc_stratixiv_arch_timing", "dart_stratixiv_arch_timing", "denoise_stratixiv_arch_timing", 
                                            "sparcT2_core_stratixiv_arch_timing", "cholesky_bdti_stratixiv_arch_timing", "minres_stratixiv_arch_timing", "stap_qrd_stratixiv_arch_timing", 
                                            "openCV_stratixiv_arch_timing", "bitonic_mesh_stratixiv_arch_timing", "segmentation_stratixiv_arch_timing", "SLAM_spheric_stratixiv_arch_timing", 
                                            "des90_stratixiv_arch_timing", "neuron_stratixiv_arch_timing", "sparcT1_core_stratixiv_arch_timing", "stereo_vision_stratixiv_arch_timing", 
                                            "cholesky_mc_stratixiv_arch_timing", "directrf_stratixiv_arch_timing", "bitcoin_miner_stratixiv_arch_timing", "LU230_stratixiv_arch_timing", 
                                            "sparcT1_chip2_stratixiv_arch_timing", "LU_Network_stratixiv_arch_timing"}; // Titan Quick Qor
    // std::vector<std::string> circuits = {"carpat_stratixiv_arch_timing", "CH_DFSIN_stratixiv_arch_timing", "CHERI_stratixiv_arch_timing", "fir_cascade_stratixiv_arch_timing", "jacobi_stratixiv_arch_timing", "JPEG_stratixiv_arch_timing", 
    //                                         "leon2_stratixiv_arch_timing", "leon3mp_stratixiv_arch_timing", "MCML_stratixiv_arch_timing", "MMM_stratixiv_arch_timing", "radar20_stratixiv_arch_timing", "random_stratixiv_arch_timing", 
    //                                         "Reed_Solomon_stratixiv_arch_timing", "smithwaterman_stratixiv_arch_timing", "stap_steering_stratixiv_arch_timing", "sudoku_check_stratixiv_arch_timing", "SURF_desc_stratixiv_arch_timing", 
    //                                         "ucsb_152_tap_fir_stratixiv_arch_timing", "uoft_raytracer_stratixiv_arch_timing", "wb_conmax_stratixiv_arch_timing", "picosoc_stratixiv_arch_timing", "murax_stratixiv_arch_timing", 
    // "EKF-SLAM_Jacobians_stratixiv_arch_timing"}; // Titan other}
    
    std::vector<std::vector<std::string>> non_existing_rr_graphs;
    std::vector<double> edge_removal_rates = {0.50, 0.65, 0.80};
    
    // Prepare thread arguments
    std::vector<std::vector<std::string>> thread_args;
    for (const std::string& circuit : circuits) {
        for (double edge_removal_rate : edge_removal_rates) {
            std::cout << circuit << " - Edge removal rate: " << edge_removal_rate << "..." << std::endl;
            
            std::string rr_graph_name = "rr_graph_" + circuit + "_" + 
                                       std::to_string(static_cast<int>(edge_removal_rate * 100)) + ".xml";
            std::string rr_graph_dir = "/home/ubuntu/titan_resources/" + rr_graph_name;
            
            if (!fs::exists(rr_graph_dir)) {
                non_existing_rr_graphs.push_back({circuit, std::to_string(edge_removal_rate)});
            } else if (circuit == "directrf_stratixiv_arch_timing" ||
                       circuit == "bitcoin_miner_stratixiv_arch_timing" ||
                       circuit == "LU_Network_stratixiv_arch_timing" ||
                       circuit == "mes_noc_stratixiv_arch_timing" ||
                       circuit == "gsm_switch_stratixiv_arch_timing" ||
                       circuit == "sparcT1_chip2_stratixiv_arch_timing") {
                continue;
            } else {
                thread_args.push_back({rr_graph_dir, circuit, std::to_string(edge_removal_rate), resource_dir});
            }
        }
    }
    
    std::cout << "Non-existing RR Graphs: ";
    for (const auto& item : non_existing_rr_graphs) {
        std::cout << item[0] << " " << item[1] << ", ";
    }
    std::cout << std::endl;
    
    // Run tasks in parallel
    std::vector<std::future<void>> futures;
    for (const auto& args : thread_args) {
        futures.push_back(std::async(std::launch::async, adjust_fan_in_out, args));
        
        // Limit concurrent tasks based on available threads
        if (futures.size() >= static_cast<size_t>(number_of_threads)) {
            for (auto& future : futures) {
                future.wait();
            }
            futures.clear();
        }
    }
    
    // Wait for remaining tasks
    for (auto& future : futures) {
        future.wait();
    }
    
    std::cout << "Done with writing all RR Graphs!" << std::endl;
    
    return 0;
}