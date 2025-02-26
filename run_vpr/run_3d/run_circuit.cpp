#include "run_circuit.h"

void run_circuit(const RunCircuitArgs& args) {
    std::string vpr_dir = args.vpr_dir;
    std::string arch_dir = args.arch_dir;
    std::string blif_file_dir = args.blif_file_dir;
    std::string net_file_dir = args.net_file_dir;
    std::string rr_graph_file_dir = args.rr_graph_file_dir;
    std::string sdc_file_dir = args.sdc_file_dir;
    std::string circuit_dir = args.circuit_dir;

    // Change working directory
    if (chdir(circuit_dir.c_str()) != 0) {
        std::cerr << "Failed to change directory to " << circuit_dir << std::endl;
        return;
    }
    std::cout << "Running in " << circuit_dir << std::endl;

    // Ensure input files exist
    if (!std::filesystem::exists(arch_dir)) {
        std::cerr << "Architecture file " << arch_dir << " does not exist" << std::endl;
        return;
    }
    if (!std::filesystem::exists(blif_file_dir)) {
        std::cerr << "BLIF file " << blif_file_dir << " does not exist" << std::endl;
        return;
    }
    if (!std::filesystem::exists(net_file_dir)) {
        std::cerr << "Net file " << net_file_dir << " does not exist" << std::endl;
        return;
    }
    if (!std::filesystem::exists(rr_graph_file_dir)) {
        std::cerr << "RR graph file " << rr_graph_file_dir << " does not exist" << std::endl;
        return;
    }
    if (!std::filesystem::exists(sdc_file_dir)) {
        std::cerr << "SDC file " << sdc_file_dir << " does not exist" << std::endl;
        return;
    }


    // Execute VPR process
    std::vector<std::string> vpr_args = { vpr_dir,
        arch_dir,
        blif_file_dir,
        "--route_chan_width", "300",
        "--max_router_iterations", "400",
        "--custom_3d_sb_fanin_fanout", "60",
        "--router_lookahead", "map",
        "--net_file", net_file_dir,
        "--read_rr_graph", rr_graph_file_dir,
        "--sdc_file", sdc_file_dir,
        "--place", "--route", "--analysis"};

    std::vector<char*> exec_args;
    for (auto& arg : vpr_args) {
        exec_args.push_back(&arg[0]);
    }
    exec_args.push_back(nullptr);

    int pid = fork();
    if (pid == 0) {
        // Child process
        freopen("vpr.out", "w", stdout);
        freopen("vpr_err.out", "w", stderr);
        execvp(exec_args[0], exec_args.data());
        perror("execvp failed");
        exit(1);
    } else if (pid > 0) {
        // Parent process
        int status;
        waitpid(pid, &status, 0);
        std::cout << circuit_dir << " is done!" << std::endl;
    } else {
        std::cerr << "Failed to fork process." << std::endl;
    }
}
