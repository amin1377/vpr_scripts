#ifndef REMOVE_INTER_DIE_CONNECTION_H
#define REMOVE_INTER_DIE_CONNECTION_H

#include <tuple>
#include <vector>
#include <string>
#include "pugixml.hpp"
#include "common_util.h"

struct RemoveInterDieConnectionArgs {
    pugi::xml_document& doc;
    double edge_removal_rate;
};

void remove_inter_die_edge(const RemoveInterDieConnectionArgs& args);

#endif