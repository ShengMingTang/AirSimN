#ifndef INCLUDE_UAVAPP_H
#define INCLUDE_UAVAPP_H

// custom includes
#include <queue>
#include <map>
#include <unordered_map>
// ns3 includes
#include "ns3/core-module.h"
#include "ns3/network-module.h"
#include "ns3/internet-module.h"
#include "ns3/point-to-point-module.h"
#include "ns3/applications-module.h"
#include "ns3/stats-module.h"
// zmq includes
#include <zmq.hpp>

// custom includes
#include "AirSimNAppBase.h"

using namespace std;
using namespace ns3;

class UavApp: public AirSimNAppBase
{
public:
    UavApp();
    virtual ~UavApp();

    /**
    * Register this type.
    * \return The TypeId.
    */
    static TypeId GetTypeId(void);
    void Setup(zmq::context_t &context,
        Ptr<Socket> socket, Address address,
        int zmqRecvPort,
        std::string name,
        Address peerAddress
    );
private:
    virtual void StartApplication (void);
    // virtual void StopApplication (void);
    Address m_peerAddress; // connected address (GCS)
};

#endif