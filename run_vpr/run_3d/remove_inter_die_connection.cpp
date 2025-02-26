#include <unordered_map>
#include "remove_inter_die_connection.h"


namespace fs = std::filesystem;

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

    std::unordered_map<int, NodeInfo> nodes;
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

        for (pugi::xml_node edge : edges_to_remove) {
            rr_edge_tag.remove_child(edge);
        }
        
        end_time = std::chrono::high_resolution_clock::now();
        execution_time = end_time - start_time;
        std::cout << "\tDone removing " << edges_to_remove.size() << " number of edges from " 
                  << rr_graph_name << " (" << execution_time.count() << " seconds)" << std::endl;
                  
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

void 

std::vector<std::pair<std::string, double>> get_remaining_rr_graph(
    const std::string& output_dir,
    const std::vector<std::string>& circuits,
    const std::vector<double>& removal_rates) {
    
    std::vector<std::pair<std::string, double>> remaining_circuits_removal_rate;
    
    for (const auto& circuit : circuits) {
        for (double removal_rate : removal_rates) {
            std::string rr_graph_name = "rr_graph_" + circuit + "_" + std::to_string(static_cast<int>(removal_rate * 100)) + ".xml";
            fs::path rr_graph_path = fs::path(output_dir) / rr_graph_name;
            
            if (!fs::exists(rr_graph_path)) {
                remaining_circuits_removal_rate.push_back({circuit, removal_rate});
            } else {
                std::cout << rr_graph_name << " already exists!" << std::endl;
            }
        }
    }
    
    return remaining_circuits_removal_rate;
}

int main(int argc, char* argv[]) {
    // Parse command line arguments
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
        std::cerr << "Usage: " << argv[0] << " --resource_dir <dir> -j <threads>" << std::endl;
        return 1;
    }
    
    fs::path rr_graph_resource_dir = fs::absolute(resource_dir);
    std::vector<std::string> circuits = {"mes_noc_stratixiv_arch_timing","dart_stratixiv_arch_timing","denoise_stratixiv_arch_timing","sparcT2_core_stratixiv_arch_timing", 
"cholesky_bdti_stratixiv_arch_timing","stap_qrd_stratixiv_arch_timing","openCV_stratixiv_arch_timing","segmentation_stratixiv_arch_timing", 
"SLAM_spheric_stratixiv_arch_timing","des90_stratixiv_arch_timing","neuron_stratixiv_arch_timing","sparcT1_core_stratixiv_arch_timing", 
"stereo_vision_stratixiv_arch_timing","cholesky_mc_stratixiv_arch_timing"}; // Titan Quick Qor
    // std::vector<std::string> circuits = {"carpat_stratixiv_arch_timing", "CH_DFSIN_stratixiv_arch_timing", "CHERI_stratixiv_arch_timing", "fir_cascade_stratixiv_arch_timing", "jacobi_stratixiv_arch_timing", "JPEG_stratixiv_arch_timing", 
    //                                         "leon2_stratixiv_arch_timing", "leon3mp_stratixiv_arch_timing", "MCML_stratixiv_arch_timing", "MMM_stratixiv_arch_timing", "radar20_stratixiv_arch_timing", "random_stratixiv_arch_timing", 
    //                                         "Reed_Solomon_stratixiv_arch_timing", "smithwaterman_stratixiv_arch_timing", "stap_steering_stratixiv_arch_timing", "sudoku_check_stratixiv_arch_timing", "SURF_desc_stratixiv_arch_timing", 
    //                                         "ucsb_152_tap_fir_stratixiv_arch_timing", "uoft_raytracer_stratixiv_arch_timing", "wb_conmax_stratixiv_arch_timing", "picosoc_stratixiv_arch_timing", "murax_stratixiv_arch_timing", 
    //                                         "EKF-SLAM_Jacobians_stratixiv_arch_timing"}; // Titan other
    
    
    std::vector<double> removal_rates = {0.05, 0.10, 0.30, 0.50, 0.65, 0.80, 0.90, 0.95, 0.98};
    auto remaining_circuits_removal_rate = get_remaining_rr_graph(resource_dir, circuits, removal_rates);
    
    std::cout << "Remaining circuits and removal rates: ";
    for (const auto& [circuit, rate] : remaining_circuits_removal_rate) {
        std::cout << circuit << "(" << rate << ") ";
    }
    std::cout << std::endl;
    
    std::vector<ThreadArg> thread_args;
    for (const auto& [circuit, removal_rate] : remaining_circuits_removal_rate) {
        std::cout << circuit << " " << removal_rate << std::endl;
        fs::path rr_graph_dir = rr_graph_resource_dir / ("rr_graph_" + circuit + ".xml");
        
        if (!fs::exists(rr_graph_dir)) {
            std::cerr << "File does not exist: " << rr_graph_dir << std::endl;
            continue;
        }
        
        thread_args.push_back({rr_graph_dir.string(), removal_rate, circuit, resource_dir});
    }
    
    // Process files in parallel using thread pool
    std::vector<std::future<void>> futures;
    
    for (const auto& arg : thread_args) {
        while (futures.size() >= static_cast<size_t>(num_threads)) {
            // Wait for a thread to finish if we've reached max threads
            for (auto it = futures.begin(); it != futures.end(); ++it) {
                if (it->wait_for(std::chrono::milliseconds(0)) == std::future_status::ready) {
                    futures.erase(it);
                    break;
                }
            }
            
            // If we still have max threads, sleep a bit
            if (futures.size() >= static_cast<size_t>(num_threads)) {
                std::this_thread::sleep_for(std::chrono::seconds(10));
            }
        }
        
        // Launch new thread
        futures.push_back(std::async(std::launch::async, remove_inter_die_edge, arg));
    }
    
    // Wait for all remaining threads to complete
    for (auto& future : futures) {
        future.wait();
    }
    
    std::cout << "Done with writing all RR Graphs!" << std::endl;
    
    return 0;
}