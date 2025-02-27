#ifndef ADJUST_3D_DRIVER_SIZE_H
#define ADJUST_3D_DRIVER_SIZE_H

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
#include "common_util.h"

struct AdjustFanInOutArgs {
    pugi::xml_document& doc;
    double mux_removal_rate;
};

void adjust_fan_in_out(const AdjustFanInOutArgs& args);

#endif
