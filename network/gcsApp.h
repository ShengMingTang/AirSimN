#ifndef INCLUDE_GCSAPP_H
#define INCLUDE_GCSAPP_H

// std includes
#include <unordered_map>
#include <vector>
#include <map>
#include <string>
#include <queue>
// ns3 includes
#include "ns3/core-module.h"
#include "ns3/network-module.h"
#include "ns3/internet-module.h"
#include "ns3/point-to-point-module.h"
#include "ns3/applications-module.h"
#include "ns3/stats-module.h"
#include "ns3/mobility-module.h"
// zmq includes
#include <zmq.hpp>

// custom includes
#include "AirSimNAppBase.h"
#include "flow.h"

using namespace std;
using namespace ns3;

class GcsApp: public AirSimNAppBase
{
public:
    GcsApp();
    virtual ~GcsApp();

    /**
    * Register this type.
    * \return The TypeId.
    */
    static TypeId GetTypeId(void);
    void Setup(zmq::context_t &context,
        Ptr<Socket> socket, Address address, 
        int zmqRecvPort,
        std::string name
    );
    
private:
    virtual void StartApplication(void);
    // virtual void StopApplication(void);
};

#endif