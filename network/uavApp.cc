// std includes
#include <fstream>
#include <sstream>
#include <limits>
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
#include "uavApp.h"
#include "AirSimSync.h"

using namespace std;
using namespace ns3;

NS_LOG_COMPONENT_DEFINE ("UavApp");

UavApp::UavApp()
{
    // Todo
}
UavApp::~UavApp()
{
    // Todo
}
TypeId UavApp::GetTypeId(void)
{
    static TypeId tid = TypeId("UavApp")
        .SetParent<Application>()
        .SetGroupName("AirSimN")
        .AddConstructor<UavApp>()
    ;
    return tid;
}

/* Init ns stuff, RPC client connection and zmq socket init, connect */
void UavApp::Setup(zmq::context_t &context,
    Ptr<Socket> socket, Address address,
    int zmqRecvPort,
    std::string name,
    Address peerAddress
)
{
    m_name = name;
    m_socket = socket;
    m_address = address;
    m_peerAddress = peerAddress;

    m_zmqSocketSend = zmq::socket_t(context, ZMQ_PUSH);
    // this port is bind by sub side
    m_zmqSocketSend.connect("tcp://localhost:" + to_string(NS2ROUTER_PORT));
    m_zmqSocketRecv = zmq::socket_t(context, ZMQ_PULL);
    m_zmqSocketRecv.connect("tcp://localhost:" + to_string(zmqRecvPort));
}
/* Bind ns sockets and logging*/
void UavApp::StartApplication(void)
{
    // ns socket routines
    m_socket->Bind();
    m_socket->SetRecvCallback(MakeCallback(&UavApp::recvCallback, this));
    m_socket->SetConnectCallback(MakeCallback(&UavApp::connectSuccCallback, this), MakeCallback(&UavApp::connectFailCallback, this));
    m_socket->SetCloseCallbacks(MakeCallback(&UavApp::closeNormCallback, this), MakeCallback(&UavApp::closeErrorCallback, this));
    if(m_socket->Connect(m_peerAddress) != 0){
        NS_FATAL_ERROR("[" << m_name << "], connect error");
    }

    m_running = true;
    NS_LOG_INFO("[" << m_name << "], starts");
}
