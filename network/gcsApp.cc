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
        .SetGroupName("ns3_AirSim")
        .AddConstructor<GcsApp>()
    ;
    return tid;
}

/* Init ns stuff, RPC client connection and zmq socket init, connect */
void GcsApp::Setup (zmq::context_t &context, Ptr<Socket> socket, Address address, 
    std::map<std::string, Ptr<ConstantPositionMobilityModel> > uavsMobility,
    int zmqRecvPort, int zmqSendPort
)
{
    m_socket = socket;
    m_address = address;
    m_uavsMobility = uavsMobility;

    m_zmqSocketSend = zmq::socket_t(context, ZMQ_PUSH);
    m_zmqSocketSend.bind("tcp://*:" + to_string(zmqSendPort));
    m_zmqSocketRecv = zmq::socket_t(context, ZMQ_REP);
    m_zmqSocketRecv.connect("tcp://localhost:" + to_string(zmqRecvPort));

    try{
        m_client.confirmConnection();
        NS_LOG_INFO("GCS connected with AirSim");
    }
    catch (rpc::rpc_error&  e) {
        std::string msg = e.get_error().as<std::string>();
        NS_LOG_INFO("Exception raised by the API, something went wrong." << std::endl << msg);
    }
}

void GcsApp::StartApplication(void)
{
    // init members
    if(m_socket->Bind(m_address)){
        NS_FATAL_ERROR("[GCS] failed to bind m_socket");
    }
    m_socket->Listen();

    // This call will disable any Send()
    // m_socket->ShutdownSend();
    
    m_socket->SetRecvCallback(
        MakeCallback(&GcsApp::recvCallback, this)
    );
    m_socket->SetAcceptCallback(
        MakeNullCallback<bool, Ptr<Socket>, const Address &>(),
        MakeCallback(&GcsApp::acceptCallback, this)
    );
    m_socket->SetCloseCallbacks(
        MakeCallback(&GcsApp::peerCloseCallback, this),
        MakeCallback(&GcsApp::peerErrorCallback, this)
    );

    mobilityUpdateDirect();
    m_running = true;
    NS_LOG_INFO("[GCS starts]");
}
void GcsApp::StopApplication(void)
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
    for(auto &it:m_connectedSockets){
        it.second->Close();
    }

    m_zmqSocketSend.close();
    m_zmqSocketRecv.close();

    NS_LOG_INFO("[GCS] stopped");
}

/*<sim_time> <name> <payload> */
void GcsApp::scheduleTx(void)
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
        std::size_t head;
        std::string name;
        const uint8_t *payload = NULL;
        int repRes = -1;

        head = message.to_string().find(' ');
        name = message.to_string().substr(0, head);
        payload = (const uint8_t*)message.data() + head + 1;

        if(m_connectedSockets.find(name) != m_connectedSockets.end()){
            Ptr<Packet> packet = Create<Packet>((const uint8_t*)payload, message.size()-(payload - (const uint8_t*)message.data()));
            repRes = m_connectedSockets[name]->Send(packet);

            if(repRes < 0){
                NS_LOG_WARN("time: " << now << ", [GCS send] to " << name << " " << packet->GetSize() << " bytes ERROR" << repRes);
            }
            else{
                NS_LOG_INFO("time: " << now << ", [GCS send] to " << name << " " << packet->GetSize() << " bytes");
            }
        }
        else{
            NS_FATAL_ERROR("[GCS drop] a packet supposed to be sent to " << name);
        }
        *(int*)rep.data() = repRes;
        m_zmqSocketRecv.send(rep, zmq::send_flags::dontwait);

        message.rebuild();
        res = m_zmqSocketRecv.recv(message, zmq::recv_flags::dontwait);
    }
}

/* <from-address> <payload> then forward to application code */
void GcsApp::recvCallback(Ptr<Socket> socket)
{
    Ptr<Packet> packet;
    Address from;
    std::size_t pos;
    std::string s;
    float now = Simulator::Now().GetSeconds();
    
    packet = socket->RecvFrom(from);
    zmq::message_t message(packet->GetSize());
    packet->CopyData((uint8_t *)message.data(), packet->GetSize());

    /* @@ We may leave the job to application */
    pos = message.to_string().find("name");
    if(pos != std::string::npos){
        std::stringstream ss(message.to_string());
        std::string name;
        ss >> name;
        ss >> name;

        m_connectedSockets[name] = socket;
        m_uavsAddress2Name[from] = name;
        if(m_socketSet.find(socket) == m_socketSet.end()){
            NS_FATAL_ERROR("[GCS] Socket map not found Error");
        }
        else{
            NS_LOG_INFO("Time:" << Simulator::Now().GetSeconds() << ", [GCS auth] from \"" << name << "\"");
        }
    }
    else{
        // forward to application code
        std::string name = m_uavsAddress2Name[from];
        std::size_t sz = name.size() + 1 + packet->GetSize();
        zmq::message_t message(sz);
        uint8_t *p = (uint8_t*)message.data();
        memcpy(p, name.c_str(), name.size());
        p += name.size();
        *p = ' ';
        p++;

        packet->CopyData(p, packet->GetSize());
        m_zmqSocketSend.send(message, zmq::send_flags::dontwait);
        NS_LOG_INFO("time: " << now << ", [GCS recv] from-" << m_uavsAddress2Name[from] << ", " << packet->GetSize() << " bytes");
    }

}
void GcsApp::acceptCallback(Ptr<Socket> s, const Address& from)
{
    // connected uavs must send their name first
    s->SetRecvCallback (MakeCallback (&GcsApp::recvCallback, this));
    m_socketSet.insert(s);
    NS_LOG_INFO("Time: " << Simulator::Now().GetSeconds() << " [GCS accept] from " << from);
}
void GcsApp::peerCloseCallback(Ptr<Socket> socket)
{
    ;
}
void GcsApp::peerErrorCallback(Ptr<Socket> socket)
{
    ;
}

void GcsApp::mobilityUpdateDirect()
{
    for(auto it:m_uavsMobility){
        msr::airlib::Kinematics::State state = m_client.simGetGroundTruthKinematics(it.first);
        float x, y, z;
        x = state.pose.position.x();
        y = state.pose.position.y();
        y = state.pose.position.z();
        ns3::Simulator::ScheduleNow(&ConstantPositionMobilityModel::SetPosition, it.second, Vector(x, y, z));
    }
}