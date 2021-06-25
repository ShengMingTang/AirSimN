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
        .SetGroupName("ns3_AirSim")
        .AddConstructor<UavApp>()
    ;
    return tid;
}

/* Init ns stuff, rPC client connection and zmq socket init, connect */
void UavApp::Setup(zmq::context_t &context, Ptr<Socket> socket, Address myAddress, Address peerAddress,
    int zmqRecvPort, int zmqSendPort, std::string name
)
{
    m_name = name;
    m_socket = socket;
    m_address = myAddress;
    m_peerAddress = peerAddress;

    m_zmqSocketSend = zmq::socket_t(context, ZMQ_PUSH);
    m_zmqSocketSend.bind("tcp://*:" + to_string(zmqSendPort));
    m_zmqSocketRecv = zmq::socket_t(context, ZMQ_REP);
    m_zmqSocketRecv.connect("tcp://localhost:" + to_string(zmqRecvPort));
}

/* Bind ns sockets and logging*/
void UavApp::StartApplication(void)
{

    // ns socket routines
    m_socket->Bind();
    m_socket->SetRecvCallback(MakeCallback(&UavApp::recvCallback, this));
    if(m_socket->Connect(m_peerAddress) != 0){
        NS_FATAL_ERROR("UAV connect error");
    };
    
    /* @@ We may leave the job to application */
    // send my name
    std::string s = "name " + m_name + " ";
    Ptr<Packet> packet = Create<Packet>((const uint8_t*)(s.c_str()), s.size()+1);
    if(m_socket->Send(packet) == -1){
        NS_FATAL_ERROR(m_name << " sends my name Error");
    }

    m_running = true;
    NS_LOG_INFO("[" << m_name << " starts]");
}
void UavApp::StopApplication(void)
{
    m_running = false;

    while(!m_events.empty()){
        EventId event = m_events.front();
        if(event.IsRunning()){
            Simulator::Cancel(event);
        }
        m_events.pop();
    }
    if(m_socket){
        m_socket->Close();
    }

    m_zmqSocketSend.close();
    m_zmqSocketRecv.close();

    NS_LOG_INFO("[" << m_name << " stopped]");
}


void UavApp::Tx(Ptr<Socket> socket, std::string payload)
{
    int ret;
    Ptr<Packet> packet = Create<Packet>((const uint8_t*)(payload.c_str()), payload.length()+1);
    if((ret = socket->Send(packet)) == -1){
        NS_LOG_WARN(m_name << " sends packet Error " << ret);
    }
}

/* <sim_time> <payload> */
void UavApp::scheduleTx(void)
{
    zmq::message_t message;
    double now = Simulator::Now().GetSeconds();
    zmq::recv_result_t res;

    zmq::message_t rep(4);

    if(!m_running){
        return;
    }

    while(!m_events.empty() && !m_events.front().IsRunning()){
        m_events.pop();
    }

    res = m_zmqSocketRecv.recv(message, zmq::recv_flags::dontwait);
    while(res.has_value() && res.value() != -1){ // EAGAIN
        int repRes = -1;
        const uint8_t *payload = NULL;

        payload = (const uint8_t*)message.data();
        Ptr<Packet> packet = Create<Packet>((const uint8_t*)payload, message.size());
        repRes = m_socket->Send(packet);

        *(int*)rep.data() = repRes;
        m_zmqSocketRecv.send(rep, zmq::send_flags::dontwait);
        if(repRes < 0){
            NS_LOG_INFO("time: " << now << " " << m_name << " sends " << packet->GetSize() << " bytes ERROR " << repRes);
        }
        else{
            NS_LOG_INFO("time: " << now << " " << m_name << " sends " << packet->GetSize() << " bytes");
        }

        message.rebuild();
        res = m_zmqSocketRecv.recv(message, zmq::recv_flags::dontwait);
    }
}
/* <from-address> <payload> then forward to application code */
void UavApp::recvCallback(Ptr<Socket> socket)
{
    Ptr<Packet> packet;
    Address from;
    float now = Simulator::Now().GetSeconds();
    packet = socket->RecvFrom(from);

    zmq::message_t message(packet->GetSize());
    packet->CopyData((uint8_t *)message.data(), packet->GetSize());
    m_zmqSocketSend.send(message, zmq::send_flags::dontwait);
    NS_LOG_INFO("time: " << now << ", [" << m_name << " recv]: " << (const char*)message.data());
}