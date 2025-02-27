#include <iostream>
#include <string>
#include <vector>
#include <algorithm>
#include <filesystem>
#include <span>
#include "pugixml.hpp"
#include "run_circuit.h"
#include "remove_inter_die_connection.h"
#include "adjust_3d_driver_size.h"
#include "analyze_rr_graph.h"

namespace fs = std::filesystem;

std::string architecture_name = "3d_SB_inter_die_stratixiv_arch.timing.xml";

// std::vector<std::string> titan_quick_qor_circuits = {
//     "gsm_switch_stratixiv_arch_timing", "mes_noc_stratixiv_arch_timing", "dart_stratixiv_arch_timing", "denoise_stratixiv_arch_timing", 
//     "sparcT2_core_stratixiv_arch_timing", "cholesky_bdti_stratixiv_arch_timing", "minres_stratixiv_arch_timing", "stap_qrd_stratixiv_arch_timing", 
//     "openCV_stratixiv_arch_timing", "bitonic_mesh_stratixiv_arch_timing", "segmentation_stratixiv_arch_timing", "SLAM_spheric_stratixiv_arch_timing", 
//     "des90_stratixiv_arch_timing", "neuron_stratixiv_arch_timing", "sparcT1_core_stratixiv_arch_timing", "stereo_vision_stratixiv_arch_timing", 
//     "cholesky_mc_stratixiv_arch_timing", "directrf_stratixiv_arch_timing", "bitcoin_miner_stratixiv_arch_timing", "LU230_stratixiv_arch_timing", 
//     "sparcT1_chip2_stratixiv_arch_timing", "LU_Network_stratixiv_arch_timing"
// };

std::vector<std::string> titan_quick_qor_circuits = {
    "gsm_switch_stratixiv_arch_timing", "mes_noc_stratixiv_arch_timing", "dart_stratixiv_arch_timing", "denoise_stratixiv_arch_timing", 
    "sparcT2_core_stratixiv_arch_timing", "cholesky_bdti_stratixiv_arch_timing", "minres_stratixiv_arch_timing", "stap_qrd_stratixiv_arch_timing", 
    "openCV_stratixiv_arch_timing", "bitonic_mesh_stratixiv_arch_timing", "segmentation_stratixiv_arch_timing", "SLAM_spheric_stratixiv_arch_timing", 
    "des90_stratixiv_arch_timing", "neuron_stratixiv_arch_timing", "sparcT1_core_stratixiv_arch_timing", "stereo_vision_stratixiv_arch_timing", 
    "cholesky_mc_stratixiv_arch_timing", "bitcoin_miner_stratixiv_arch_timing", "sparcT1_chip2_stratixiv_arch_timing", "LU_Network_stratixiv_arch_timing"
};

std::vector<std::string> titan_other_circuits = {
    "carpat_stratixiv_arch_timing", "CH_DFSIN_stratixiv_arch_timing", "CHERI_stratixiv_arch_timing", "EKF-SLAM_Jacobians_stratixiv_arch_timing", 
    "fir_cascade_stratixiv_arch_timing", "jacobi_stratixiv_arch_timing", "JPEG_stratixiv_arch_timing", "leon2_stratixiv_arch_timing", 
    "leon3mp_stratixiv_arch_timing", "MCML_stratixiv_arch_timing", "MMM_stratixiv_arch_timing", "radar20_stratixiv_arch_timing", 
    "random_stratixiv_arch_timing", "Reed_Solomon_stratixiv_arch_timing", "smithwaterman_stratixiv_arch_timing", "stap_steering_stratixiv_arch_timing", 
    "sudoku_check_stratixiv_arch_timing", "SURF_desc_stratixiv_arch_timing", "ucsb_152_tap_fir_stratixiv_arch_timing", 
    "uoft_raytracer_stratixiv_arch_timing", "wb_conmax_stratixiv_arch_timing", "picosoc_stratixiv_arch_timing", "murax_stratixiv_arch_timing"
};

// std::vector<std::string> titan_other_circuits = {"ucsb_152_tap_fir_stratixiv_arch_timing"};

std::vector<double> edge_removal_rates = {0, 0.3, 0.5, 0.6, 0.7, 0.8, 0.9};
std::vector<double> mux_removal_rates = {0, 0.3, 0.5, 0.6, 0.7, 0.8, 0.9};

// std::vector<double> edge_removal_rates = {0, 0.5};
// std::vector<double> mux_removal_rates = {0, 0.5};


struct Parameters {
    std::string vtr_root_dir;
    std::string resource_dir;
    std::vector<std::string> benchmarks;
    int num_threads;
};

struct ThreadArg {
    std::string vpr_dir;
    std::string arch_name;
    std::string resource_dir;
    double edge_removal_rate;
    double mux_removal_rate;
    std::string circuit;
    std::string output_dir;
    std::string benchmark_name;
};

bool initialize_parameters(int argc, char* argv[], Parameters& params) {
    std::span args(argv, argc);
    for (size_t i = 1; i < args.size(); ++i) {
        std::string arg = args[i];

        if (arg == "--vtr_root_dir" && i + 1 < args.size()) params.vtr_root_dir = args[++i];
        else if (arg == "--resource_dir" && i + 1 < args.size()) params.resource_dir = args[++i];
        else if (arg == "--benchmarks") {
            while (i + 1 < args.size() && args[i + 1][0] != '-') {
                params.benchmarks.push_back(args[++i]);
            }
        }
        else if (arg == "--num_threads" && i + 1 < args.size()) params.num_threads = std::stoi(args[++i]);
        else {
            std::cerr << "Unknown argument: " << arg << "\n";
            return false;
        }
    }

    if (params.vtr_root_dir.empty() || params.resource_dir.empty() || params.benchmarks.empty() || params.num_threads <= 0) {
        std::cerr << "Usage: " << args[0] << " --vtr_root_dir <path> --resource_dir <path> --benchmarks <name1> <name2> ... --num_threads <num>\n";
        return false;
    }
    return true;
}


void run_circuit(const ThreadArg& thread_arg) {
    std::string vpr_dir = thread_arg.vpr_dir;
    std::string arch_name = thread_arg.arch_name;
    std::string resource_dir = thread_arg.resource_dir;
    double edge_removal_rate = thread_arg.edge_removal_rate;
    double mux_removal_rate = thread_arg.mux_removal_rate;
    std::string circuit = thread_arg.circuit;
    std::string output_dir = thread_arg.output_dir;
    std::string benchmark_name = thread_arg.benchmark_name;

    if (chdir(output_dir.c_str()) != 0) {
        std::cerr << "Failed to change directory to " << output_dir << std::endl;
        exit(1);
    }

    std::string original_rr_graph_name = "rr_graph_" + circuit +".xml";
    std::string original_rr_graph_file_dir = resource_dir + "/" + original_rr_graph_name;
    std::string modified_rr_graph_name = "rr_graph_" + circuit + "_" + std::to_string(static_cast<int>(edge_removal_rate * 100)) + "_" + std::to_string(static_cast<int>(mux_removal_rate * 100)) + ".xml";

    std::cout << "Start working on " << modified_rr_graph_name << "..." << std::endl;

    auto start_time = std::chrono::high_resolution_clock::now();
    pugi::xml_document doc;
    pugi::xml_parse_result result = doc.load_file(original_rr_graph_file_dir.c_str());
    if (!result) {
        std::cerr << "XML parsing error: " << result.description() << std::endl;
        return;
    }
    auto end_time = std::chrono::high_resolution_clock::now();
    auto execution_time = std::chrono::duration_cast<std::chrono::microseconds>(end_time - start_time).count() / 1000000.0;
    std::cout << "\tParsing " << original_rr_graph_name << " is done (" << execution_time << " seconds)!" << std::endl;

    start_time = std::chrono::high_resolution_clock::now();
    RemoveInterDieConnectionArgs remove_inter_die_connection_args = {
        .doc = doc,
        .edge_removal_rate = edge_removal_rate
    };
    remove_inter_die_edge(remove_inter_die_connection_args);
    end_time = std::chrono::high_resolution_clock::now();
    execution_time = std::chrono::duration_cast<std::chrono::microseconds>(end_time - start_time).count() / 1000000.0;
    std::cout << "\t" << modified_rr_graph_name << " removing inter-die connections is done (" << execution_time << " seconds)!" << std::endl;

    start_time = std::chrono::high_resolution_clock::now();
    AdjustFanInOutArgs adjust_fan_in_out_args = {
        .doc = doc,
        .mux_removal_rate = mux_removal_rate
    };
    adjust_fan_in_out(adjust_fan_in_out_args);
    end_time = std::chrono::high_resolution_clock::now();
    execution_time = std::chrono::duration_cast<std::chrono::microseconds>(end_time - start_time).count() / 1000000.0;
    std::cout << "\t" << modified_rr_graph_name << " adjusting fan-in/out is done (" << execution_time << " seconds)!" << std::endl;

    std::cout << "\tStart writing " << modified_rr_graph_name << std::endl;
    start_time = std::chrono::high_resolution_clock::now();
    fs::path rr_graph_output_path = fs::path(output_dir) / modified_rr_graph_name;
    bool save_result = doc.save_file(rr_graph_output_path.string().c_str());
    if (!save_result) {
        std::cerr << "Failed to save XML file: " << rr_graph_output_path << std::endl;
    }
    end_time = std::chrono::high_resolution_clock::now();
    execution_time = std::chrono::duration_cast<std::chrono::microseconds>(end_time - start_time).count() / 1000000.0;
    std::cout << "\tDone writing " << modified_rr_graph_name << " (" << execution_time << " seconds)!" << std::endl;

    std::cout << "\tStart analyzing " << modified_rr_graph_name << "..." << std::endl;
    start_time = std::chrono::high_resolution_clock::now();
    AnalyzeRRGraphArgs analyze_rr_graph_args = {
        .rr_graph_dir = modified_rr_graph_name
    };
    analyze_rr_graph(analyze_rr_graph_args);
    end_time = std::chrono::high_resolution_clock::now();
    execution_time = std::chrono::duration_cast<std::chrono::microseconds>(end_time - start_time).count() / 1000000.0;
    std::cout << "\tDone analyzing " << modified_rr_graph_name << " (" << execution_time << " seconds)!" << std::endl;

    std::cout << "Start running VPR for " << modified_rr_graph_name << "..." << std::endl;
    start_time = std::chrono::high_resolution_clock::now();
    RunCircuitArgs args = {
        .vpr_dir = vpr_dir,
        .arch_dir = resource_dir + "/" + arch_name,
        .blif_file_dir = resource_dir + "/" + circuit + ".blif",
        .net_file_dir = resource_dir + "/" + circuit + ".net",
        .rr_graph_file_dir = modified_rr_graph_name,
        .sdc_file_dir = resource_dir + "/" + circuit + ".sdc",
        .benchmark_name = benchmark_name
    };
    run_circuit(args);
    end_time = std::chrono::high_resolution_clock::now();
    execution_time = std::chrono::duration_cast<std::chrono::microseconds>(end_time - start_time).count() / 1000000.0;
    std::cout << "Done running VPR for " << modified_rr_graph_name << " (" << execution_time << " seconds)!" << std::endl;

    try {
        if (std::filesystem::remove(rr_graph_output_path)) {
            std::cout << "File '" << rr_graph_output_path << "' deleted successfully.\n";
        } else {
            std::cout << "File '" << rr_graph_output_path << "' does not exist.\n";
        }
    } catch (const std::filesystem::filesystem_error& e) {
        std::cerr << "Error: " << e.what() << '\n';
    }
}

int main(int argc, char* argv[]) {
    Parameters params;
    if (!initialize_parameters(argc, argv, params)) {
        return 1;
    }

    for (const auto& benchmark : params.benchmarks) {   
        std::cout << "Running with: " << "VTR_ROOT_DIR=" << params.vtr_root_dir << " RESOURCE_DIR=" << params.resource_dir << 
        " BENCHMARK=" << benchmark << " NUM_THREADS=" << params.num_threads << std::endl;
    }

    std::string vpr_dir = params.vtr_root_dir + "/vpr/vpr";
    std::string titan_quick_qor_dir = params.vtr_root_dir + "/vtr_flow/tasks/regression_tests/vtr_reg_nightly_test7/3d_sb_titan_quick_qor_auto_bb";
    std::string titan_other_dir = params.vtr_root_dir + "/vtr_flow/tasks/regression_tests/vtr_reg_nightly_test7/3d_sb_titan_other_auto_bb";

    std::vector<ThreadArg> thread_args;
    for (const auto& benchmark : params.benchmarks) {
        std::string run_dir;
        std::vector<std::string> circuit_list;
        if (benchmark == "titan_quick_qor") {
            run_dir = titan_quick_qor_dir;
            circuit_list = titan_quick_qor_circuits;
        } else if (benchmark == "titan_other") {
            run_dir = titan_other_dir;
            circuit_list = titan_other_circuits;
        }
        int run_num = 2;
        for (const auto& edge_removal_rate : edge_removal_rates) {
            for (const auto& mux_removal_rate : mux_removal_rates) {
                for (const auto& circuit : circuit_list) {
                    std::ostringstream ss;
                    ss << "run" << std::setfill('0') << std::setw(3) << run_num;
                    std::string run_dir_name = ss.str();
                    std::string circuit_dir = run_dir + "/" + run_dir_name + "/" + architecture_name + "/" + circuit + ".blif" + "/common";
                    try {
                        if (std::filesystem::create_directories(circuit_dir)) {
                    std::cout << "Directory created: " << circuit_dir << std::endl;
                    } else {
                        std::cout << "Directory " << circuit_dir << " already exists or couldn't be created." << std::endl;
                    }
                    } catch (const std::filesystem::filesystem_error& e) {
                        std::cerr << "Error creating directory: " << e.what() << std::endl;
                    }
                    thread_args.push_back({vpr_dir, architecture_name, params.resource_dir, edge_removal_rate, mux_removal_rate, circuit, circuit_dir, benchmark});
                }
                run_num++;
            }
        }
    }

    std::vector<pid_t> active_processes;
    for (int i = 0; i < std::min(params.num_threads, static_cast<int>(thread_args.size())); ++i) {
        pid_t pid = fork();
        if (pid == 0) {
            run_circuit(thread_args[i]);
            exit(0);
        } else if (pid > 0) {
            active_processes.push_back(pid);
        } else {
            std::cerr << "Failed to fork process." << std::endl;
        }
    }

    static size_t next_circuit_idx = params.num_threads;
    while (!active_processes.empty()) {
        int status;
        pid_t finished_pid = wait(&status);
        active_processes.erase(std::remove(active_processes.begin(), active_processes.end(), finished_pid), active_processes.end());

        if (active_processes.size() < params.num_threads) {
            while (next_circuit_idx < thread_args.size() && active_processes.size() < params.num_threads) {
                pid_t pid = fork();
                if (pid == 0) {
                    run_circuit(thread_args[next_circuit_idx]);
                    exit(0);
                } else if (pid > 0) {
                    active_processes.push_back(pid);
                }
                ++next_circuit_idx;
            }
        }
    }

    return 0;

}