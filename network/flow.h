#ifndef INCLUDE_FLOW_H
#define INCLUDE_FLOW_H
#include <string>

#define FLOWOP_SEND "SEND"
#define FLOWOP_RECV "RECV"
#define FLOWOP_STOP "STOP"

namespace flow{

struct Flow
{
    Flow(int id, uint32_t size, std::string dst):
    id{id}, left{size}, dst{dst}
    {}
    Flow() {}
    
    int id;
    uint32_t left;
    std::string dst;
};

}
#endif