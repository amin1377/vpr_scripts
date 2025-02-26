#include <iostream>
#include <string>
#include <vector>
#include <set>
#include <random>
#include <algorithm>
#include <filesystem>
#include "pugixml.hpp"


struct ThreadArg {
    std::string resource_dir;
    double edge_removal_rate;
    double mux_removal_rate;
    std::string circuit;
    std::string output_dir;
};


void run_circuit(const ThreadArg& thread_arg) {
    std::string resource_dir = thread_arg.resource_dir;
    double edge_removal_rate = thread_arg.edge_removal_rate;
    double mux_removal_rate = thread_arg.mux_removal_rate;
    std::string circuit = thread_arg.circuit;
    std::string output_dir = thread_arg.output_dir;

    std::string original_rr_graph_name = "rr_graph_" + circuit +".xml";
    std::string original_rr_graph_file_dir = resource_dir + "/" + original_rr_graph_name;
    std::string modified_rr_graph_name = "rr_graph_" + circuit + "_" + std::to_string(static_cast<int>(edge_removal_rate * 100)) + "_" + std::to_string(static_cast<int>(mux_removal_rate * 100)) + ".xml";

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
    rr_graph_remove_inter_die_connection(doc, edge_removal_rate);
    end_time = std::chrono::high_resolution_clock::now();
    execution_time = std::chrono::duration_cast<std::chrono::microseconds>(end_time - start_time).count() / 1000000.0;
    std::cout << "\t" << modified_rr_graph_name << " removing inter-die connections is done (" << execution_time << " seconds)!" << std::endl;

    start_time = std::chrono::high_resolution_clock::now();
    rr_graph_adjust_fan_in_out(doc, mux_removal_rate);
    end_time = std::chrono::high_resolution_clock::now();
    execution_time = std::chrono::duration_cast<std::chrono::microseconds>(end_time - start_time).count() / 1000000.0;
    std::cout << "\t" << modified_rr_graph_name << " adjusting fan-in/out is done (" << execution_time << " seconds)!" << std::endl;

    std::cout << "\tStart writing " << modified_rr_graph_name << std::endl;
    start_time = std::chrono::high_resolution_clock::now();
    fs::path output_path = fs::path(output_dir) / modified_rr_graph_name;
    bool save_result = doc.save_file(output_path.string().c_str());
    if (!save_result) {
        std::cerr << "Failed to save XML file: " << output_path << std::endl;
    }
    end_time = std::chrono::high_resolution_clock::now();
    execution_time = std::chrono::duration_cast<std::chrono::microseconds>(end_time - start_time).count() / 1000000.0;
    std::cout << "\tDone writing " << modified_rr_graph_name << " (" << execution_time << " seconds)!" << std::endl;

    std::cout << "Writing " << modified_rr_graph_name << " is complete!" << std::endl;

}

int main(int argc, char* argv[]) {

}