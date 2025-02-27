#include <sys/resource.h>
#include <fstream>
#include <string>
#include "common_util.h"

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

double getPeakMemoryUsageMB() {
    struct rusage usage;
    getrusage(RUSAGE_SELF, &usage);
    return static_cast<double>(usage.ru_maxrss) / 1024.0; // MB
}

double getCurrentMemoryUsageMB() {
    std::ifstream file("/proc/self/status");
    std::string line;
    while (std::getline(file, line)) {
        if (line.find("VmRSS:") != std::string::npos) {
            long memory_kb;
            sscanf(line.c_str(), "VmRSS: %ld kB", &memory_kb);
            return static_cast<double>(memory_kb) / 1024.0; // MB
        }
    }
    return 0.0;
}