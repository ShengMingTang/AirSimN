#ifndef INCLUDE_GCSAPP_H
#define INCLUDE_GCSAPP_H


// std includes
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
// AirSim includes
#include "common/common_utils/StrictMode.hpp"
STRICT_MODE_OFF
#ifndef RPCLIB_MSGPACK
#define RPCLIB_MSGPACK clmdep_msgpack
#endif // !RPCLIB_MSGPACK
#include "rpc/rpc_error.h"
STRICT_MODE_ON
#include "vehicles/multirotor/api/MultirotorRpcLibClient.hpp"
#include "common/common_utils/FileSystem.hpp"
// zmq includes
#include <zmq.hpp>

using namespace std;
using namespace ns3;

class GcsApp: public Application
{
public:
    GcsApp();
    virtual ~GcsApp();

    /**
    * Register this type.
    * \return The TypeId.
    */
    static TypeId GetTypeId (void);
    void Setup (zmq::context_t &context, Ptr<Socket> socket, Address address, 
        std::map<std::string, Ptr<ConstantPositionMobilityModel> > uavsMobility,
        int zmqRecvPort, int zmqSendPort
    );
    void scheduleTx(void);
    void mobilityUpdateDirect(); // direct message from AirSim not UAVs

private:
    virtual void StartApplication (void);
    virtual void StopApplication (void);

    void Tx(Ptr<Socket> socket, Ptr<Packet> packet) {socket->Send(packet);}

    // socket callbacks
    void acceptCallback(Ptr<Socket> s, const Address& from);
    void recvCallback(Ptr<Socket> socket);
    void peerCloseCallback(Ptr<Socket> socket);
    void peerErrorCallback(Ptr<Socket> socket);

    // ns stuffs
    bool m_running = false;
    Ptr<Socket>     m_socket;
    Address m_address;
    std::queue<EventId> m_events;
    
    std::set< Ptr<Socket> > m_socketSet; // update on accept()
    std::map<Address, std::string> m_uavsAddress2Name;
    std::map< std::string, Ptr<Socket> > m_connectedSockets;
    
    // use their names to refer to AirSim vehicle key and update mobility directly
    std::map< std::string, Ptr<ConstantPositionMobilityModel> > m_uavsMobility;

    // custom application member
    zmq::socket_t m_zmqSocketSend;
    zmq::socket_t m_zmqSocketRecv;
    msr::airlib::MultirotorRpcLibClient m_client;
};

#endif