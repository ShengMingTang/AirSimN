// std includes
#include <fstream>
#include <map>
#include <string>
#include <cstring>
// ns3 includes
#include "ns3/core-module.h"
#include "ns3/network-module.h"
#include "ns3/internet-module.h"
#include "ns3/point-to-point-module.h"
#include "ns3/applications-module.h"
#include "ns3/stats-module.h"
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
// custom includes
#include "gcsApp.h"
#include "AirSimSync.h"

using namespace std;
using namespace ns3;

NS_LOG_COMPONENT_DEFINE("GcsApp");

GcsApp::GcsApp()
{
    // Todo
}
GcsApp::~GcsApp()
{
    // Todo
}
TypeId GcsApp::GetTypeId(void)
{
    static TypeId tid = TypeId("GcsApp")
        .SetParent<Application>()
        .SetGroupName("AirSimN")
        .AddConstructor<GcsApp>()
    ;
    return tid;
}

/* Init ns stuff, RPC client connection and zmq socket init, connect */
void GcsApp::Setup(zmq::context_t &context,
    Ptr<Socket> socket, Address address, 
    int zmqRecvPort,
    std::string name
)
{
    m_socket = socket;
    m_address = address;

    m_zmqSocketSend = zmq::socket_t(context, ZMQ_PUSH);
    m_zmqSocketSend.connect("tcp://localhost:" + to_string(NS2ROUTER_PORT));
    
    m_zmqSocketRecv = zmq::socket_t(context, ZMQ_PULL);
    m_zmqSocketRecv.connect("tcp://localhost:" + to_string(zmqRecvPort));

    m_name = name;
}

void GcsApp::StartApplication(void)
{
    // init members
    if(m_socket->Bind(m_address)){
        NS_FATAL_ERROR("[GCS] failed to bind m_socket");
    }
    m_socket->Listen();
    
    m_socket->SetAcceptCallback(
        MakeNullCallback<bool, Ptr<Socket>, const Address &>(),
        MakeCallback(&GcsApp::acceptCallback, this)
    );
    m_socket->SetCloseCallbacks(
        MakeCallback(&GcsApp::closeNormCallback, this),
        MakeCallback(&GcsApp::closeErrorCallback, this)
    );

    m_running = true;
    NS_LOG_INFO("[" << m_name << "], starts");
}
