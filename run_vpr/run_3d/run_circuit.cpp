#include "run_circuit.h"

void run_circuit(const RunCircuitArgs& args) {
    std::string vpr_dir = args.vpr_dir;
    std::string arch_dir = args.arch_dir;
    std::string blif_file_dir = args.blif_file_dir;
    std::string net_file_dir = args.net_file_dir;
    std::string rr_graph_file_dir = args.rr_graph_file_dir;
    std::string sdc_file_dir = args.sdc_file_dir;
    std::string benchmark_name = args.benchmark_name;
    std::string device_name = args.device_name;

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


    // Execute VPR process
    std::vector<std::string> vpr_args;
    if (benchmark_name == "titan_quick_qor") {
        if (!std::filesystem::exists(sdc_file_dir)) {
            std::cerr << "SDC file " << sdc_file_dir << " does not exist" << std::endl;
            return;
        }
        vpr_args = {vpr_dir,
        arch_dir,
        blif_file_dir,
        "--route_chan_width", "300",
        "--max_router_iterations", "400",
        "--custom_3d_sb_fanin_fanout", "60",
        "--router_lookahead", "map",
        "--net_file", net_file_dir,
        "--read_rr_graph", rr_graph_file_dir,
        "--sdc_file", sdc_file_dir,
        "--initial_pres_fac", "1.0",
        "--router_profiler_astar_fac", "1.5",
        "--seed", "3",
        "--verify_file_digests", "off",
        "--place", "--route", "--analysis"};
    } else if (benchmark_name == "titan_other") {
        if (!std::filesystem::exists(sdc_file_dir)) {
            std::cerr << "SDC file " << sdc_file_dir << " does not exist" << std::endl;
            return;
        }
        vpr_args = {vpr_dir,
        arch_dir,
        blif_file_dir,
        "--route_chan_width", "300",
        "--max_router_iterations", "400",
        "--custom_3d_sb_fanin_fanout", "60",
        "--router_lookahead", "map",
        "--net_file", net_file_dir,
        "--read_rr_graph", rr_graph_file_dir,
        "--sdc_file", sdc_file_dir,
        "--verify_file_digests", "off",
        "--place", "--route", "--analysis"};
    } else if (benchmark_name == "koios") {
        if (device_name.empty()) {
            std::cerr << "Device name is empty for benchmark " << benchmark_name << std::endl;
            return;
        }
        vpr_args = {vpr_dir,
        arch_dir,
        blif_file_dir,
        "--device", device_name,
        "--route_chan_width", "320",
        "--max_router_iterations", "200",
        "--net_file", net_file_dir,
        "--read_rr_graph", rr_graph_file_dir,
        "--verify_file_digests", "off",
        "--custom_3d_sb_fanin_fanout", "60",
        "--place", "--route", "--analysis"};
    } else {
        std::cerr << "Invalid benchmark name: " << benchmark_name << std::endl;
        return;
    }

    std::vector<char*> exec_args;
    for (auto& arg : vpr_args) {
        exec_args.push_back(&arg[0]);
    }
    exec_args.push_back(nullptr);

    int timeout;
    if (benchmark_name == "titan_quick_qor") {
        timeout = 18000;
    } else if (benchmark_name == "titan_other") {
        timeout = 7200;
    } else if (benchmark_name == "koios") {
        timeout = 18000;
    } else {
        std::cerr << "Invalid benchmark name: " << benchmark_name << std::endl;
        return;
    }
    int pid = fork();
    if (pid == 0) {
        // Child process
        if (freopen("vpr.out", "w", stdout) == nullptr) {
            std::cerr << "Failed to open vpr.out" << std::endl;
            exit(1);
        }
        if (freopen("vpr_err.out", "w", stderr) == nullptr) {
            std::cerr << "Failed to open vpr_err.out" << std::endl;
            exit(1);
        }
        execvp(exec_args[0], exec_args.data());
        perror("execvp failed");
        exit(1);
    } else if (pid > 0) {
        // Parent process
        int status;
        time_t start_time = time(nullptr);
        time_t end_time;
        while (true) {
            end_time = time(nullptr);
            if (difftime(end_time, start_time) >= timeout) {
                kill(pid, SIGKILL);
                std::cerr << "RR Graph: "<< rr_graph_file_dir << "Timeout: " << timeout << " seconds" << std::endl;
                exit(1);
            } else {
                auto result = waitpid(pid, &status, WNOHANG);
                if (result == pid) {
                    break;
                }
            }
            sleep(1);
        }
    } else {
        std::cerr << "Failed to fork process." << std::endl;
    }
}
