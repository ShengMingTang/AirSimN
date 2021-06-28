#ifndef INCLUDE_APP_H
#define INCLUDE_APP_H

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
#include "flow.h"

using namespace std;
using namespace ns3;

class AirSimNAppBase: public Application
{
public:
    AirSimNAppBase();
    virtual ~AirSimNAppBase();

    // Deleted since we make it virtual
    // static TypeId GetTypeId(void) = 0;

    // Setup() is not defined here
    void processReq(void);
protected:
    // socket callbacks
    virtual void acceptCallback(Ptr<Socket> socket, const Address& from);
    virtual void sendCallback(Ptr<Socket> socket, uint32_t txSpace);
    virtual void recvCallback(Ptr<Socket> socket);
    virtual void connectSuccCallback(Ptr<Socket> socket);
    virtual void connectFailCallback(Ptr<Socket> socket);
    virtual void closeNormCallback(Ptr<Socket> socket);
    virtual void closeErrorCallback(Ptr<Socket> socket);
    void sendName(Ptr<Socket> socket);

    // flow related
    void triggerFlow(Ptr<Socket> socket);

    // ns stuff
    bool m_running = false;
    Ptr<Socket> m_socket; // for UAV: to connect to others, for GCS: the listening socket
    Address m_address; // self address
    std::map<Address, std::string> m_address2Name; // update on receiving first message from others
    std::map< std::string, Ptr<Socket> > m_name2Socket; // update together with m_address2Name
    std::map< Ptr<Socket>, std::string > m_socket2Name; // update together with m_address2Name

    // custom application member, ZMQ stuff
    std::string m_name; // name of this application
    zmq::socket_t m_zmqSocketSend; // send message to py app
    zmq::socket_t m_zmqSocketRecv; // recv message from py app
    
    // Flow related
    std::set<Address> m_addressKnown; // in set, don't read packet, else read and record to m_connectedSockets
    std::unordered_map<int, flow::Flow> m_flows; // flow.id to flows
    std::map<Ptr<Socket>, std::queue<int> > m_flows2Dst; // socket to flow
private:
    virtual void StartApplication(void) = 0;
    virtual void StopApplication(void);
};

#endif