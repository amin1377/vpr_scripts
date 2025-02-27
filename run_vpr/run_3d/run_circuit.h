#ifndef RUN_CIRCUIT_H
#define RUN_CIRCUIT_H

#include <iostream>
#include <vector>
#include <string>
#include <filesystem>
#include <unistd.h>
#include <sys/types.h>
#include <sys/wait.h>
#include <fstream>

struct RunCircuitArgs {
    std::string vpr_dir;
    std::string arch_dir;
    std::string blif_file_dir;
    std::string net_file_dir;
    std::string rr_graph_file_dir;
    std::string sdc_file_dir;
};

void run_circuit(const RunCircuitArgs& args);

#endif