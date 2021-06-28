// std includes
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
// zmq includes
#include <zmq.hpp>
// custom includes
#include "AirSimNAppBase.h"
#include "AirSimSync.h"

using namespace std;
using namespace ns3;

NS_LOG_COMPONENT_DEFINE("AirSimNAppBase");

AirSimNAppBase::AirSimNAppBase()
{
    // TODO
}
AirSimNAppBase::~AirSimNAppBase()
{
    // TODO
}
/* Simply set RecvCallback and log */
void AirSimNAppBase::acceptCallback(Ptr<Socket> socket, const Address& from)
{
    // connected uavs must send their name first
    socket->SetRecvCallback(MakeCallback(&AirSimNAppBase::recvCallback, this));
    socket->SetConnectCallback(
        MakeCallback(&AirSimNAppBase::connectSuccCallback, this), 
        MakeCallback(&AirSimNAppBase::connectFailCallback, this)
    );
    socket->SetCloseCallbacks(MakeCallback(&AirSimNAppBase::closeNormCallback, this), MakeCallback(&AirSimNAppBase::closeErrorCallback, this));
    sendName(socket);
    socket->SetSendCallback(MakeCallback(&AirSimNAppBase::sendCallback, this));
    NS_LOG_INFO("[NS Time: " << Simulator::Now().GetSeconds() << "], [" << m_name << " accept] from " << from);
}
/* Trigger next or continue the current one */
void AirSimNAppBase::sendCallback(Ptr<Socket> socket, uint32_t txSpace)
{
    triggerFlow(socket);
}
/*
Auth or forward to application code
<src> <dst(this)> "RECV" <size>
*/
void AirSimNAppBase::recvCallback(Ptr<Socket> socket)
{
    Ptr<Packet> packet;
    Address from;
    
    packet = socket->RecvFrom(from);

    // auth read
    if(m_addressKnown.find(from) == m_addressKnown.end()){
        std::string s(packet->GetSize(), ' ');
        std::string name;
        packet->CopyData((uint8_t*)s.data(), packet->GetSize());
        std::stringstream ss(s);
        ss >> name;
        m_address2Name[from] = name;
        m_name2Socket[name] = socket;
        m_socket2Name[socket] = name;

        m_addressKnown.insert(from);
        NS_LOG_INFO("[NS Time:" << Simulator::Now().GetSeconds() << " ], [" << m_name << " auth] from \"" << name << "\"");
    }
    else{ // don't read, we have known who it is, forward to py application 
        std::stringstream ss;
        std::string s;

        ss << m_address2Name[from] << " " << m_name << " " << FLOWOP_RECV << " " << packet->GetSize();
        s = ss.str();
        zmq::message_t message(s.size());
        memcpy((uint8_t*)(message.data()), s.data(), s.size());
        m_zmqSocketSend.send(message, zmq::send_flags::dontwait);
        NS_LOG_INFO("[ NS Time: " << Simulator::Now().GetSeconds() << "], [" << m_name  << " recv] from-" << m_address2Name[from] << ", " << packet->GetSize() << " bytes");
    }
}
void AirSimNAppBase::connectSuccCallback(Ptr<Socket> socket)
{
    sendName(socket);
}
void AirSimNAppBase::connectFailCallback(Ptr<Socket> socket)
{
    NS_FATAL_ERROR("[" << m_name << "], connect Fail");
}
void AirSimNAppBase::closeNormCallback(Ptr<Socket> socket)
{
    for(auto it:m_name2Socket){
        if(it.second == socket){
            NS_LOG_INFO("[" << m_name << "], connection to " << it.first << "Closed");
        }
    }
}
void AirSimNAppBase::closeErrorCallback(Ptr<Socket> socket)
{
    for(auto it:m_name2Socket){
        if(it.second == socket){
            NS_FATAL_ERROR("[" << m_name << "], connection to " << it.first << "Close Error");
        }
    }
}
void AirSimNAppBase::sendName(Ptr<Socket> socket)
{
    std::string s(m_name);
    Ptr<Packet> packet = Create<Packet>((const uint8_t*)(s.c_str()), s.size()+1);
    if(socket->Send(packet) < 0){
        NS_FATAL_ERROR(m_name << " sends its name Error");
    }
    else{
        NS_LOG_INFO(m_name << " sends its name to " << m_socket2Name[socket]);
    }
}

/*
Either keep transmitting the current flow or auto trigger the next one
<src(this)> <dst> "SEND" <size>
*/
void AirSimNAppBase::triggerFlow(Ptr<Socket> socket)
{
    // clear completed flows if any
    while(!m_flows2Dst[socket].empty() && m_flows[m_flows2Dst[socket].front()].left <= 0){
        NS_LOG_INFO("Trigger flow pop");
        m_flows2Dst[socket].pop();
        m_flows.erase(m_flows2Dst[socket].front());
    }
    if(!m_flows2Dst[socket].empty()){
        NS_LOG_INFO("Trigger flow trigger");
        int fid = m_flows2Dst[socket].front();
        NS_LOG_INFO("Trigger flow trigger");
        for(auto it:m_flows){
            // NS_LOG_INFO("Flow " << it.first << " " << it.second.id << " " << it.second.left << " " << it.second.dst);
            NS_LOG_INFO(m_name << " Flow " << it.first);
        }
        int size = std::min(socket->GetTxAvailable(), m_flows[fid].left);
        NS_LOG_INFO("Trigger flow trigger " << m_flows[fid].left);
        Ptr<Packet> packet = Create<Packet>(size);
        NS_LOG_INFO("Trigger flow trigger");
        
        int res = socket->Send(packet);
        if(res >= 0){
            m_flows[fid].left -= size;
        }

        NS_LOG_INFO("Trigger flow trigger report");
        // report to py app
        std::stringstream ss;
        std::string s;
        ss << m_name << " " << m_socket2Name[socket] << " " << FLOWOP_SEND << " " << packet->GetSize();
        s = ss.str();
        zmq::message_t message(s.size());

        NS_LOG_INFO("Trigger flow memcpy");
        memcpy((uint8_t*)(message.data()), s.data(), s.size());
        m_zmqSocketSend.send(message, zmq::send_flags::dontwait);
        NS_LOG_INFO("[ NS Time: " << Simulator::Now().GetSeconds() << "], [" << m_name  << " send] to " << m_socket2Name[socket] << ", " << packet->GetSize() << " bytes");
    }
    NS_LOG_INFO("Trigger flow return");
}

/*
<flowid> "SEND" <size> <dst>
*/
void AirSimNAppBase::processReq(void)
{
    zmq::message_t message;
    zmq::recv_result_t res;

    if(!m_running){
        return;
    }

    res = m_zmqSocketRecv.recv(message, zmq::recv_flags::dontwait);
    while(res.has_value() && res.value() != -1){ // not EAGAIN
        int fid;
        std::stringstream ss(message.to_string());
        std::string op, args;
        
        NS_LOG_INFO("[" << m_name << "] " << ss.str());
        ss >> fid >> op;
        
        if(op == FLOWOP_SEND){
            int size;
            std::string dst;
            Ptr<Socket> socket;

            ss >> size >> dst;
            socket = m_name2Socket[dst];

            flow::Flow f(fid, size, dst);
            m_flows[fid] = f;
            if(m_flows2Dst.find(socket) != m_flows2Dst.end()){
                m_flows2Dst[socket] = std::queue<int>();
            }
            m_flows2Dst[socket].push(fid);
            NS_LOG_INFO("Trigger flow");
            triggerFlow(socket);
        }
        else{
            NS_FATAL_ERROR("op:" << op << " not handled");
        }
        message.rebuild();
    }
}
void AirSimNAppBase::StopApplication(void)
{
    m_running = false;

    if(m_socket){
        m_socket->Close();
    }
    for(auto it:m_name2Socket){
        if(it.second){
            it.second->Close();
        }
    }

    m_zmqSocketSend.close();
    m_zmqSocketRecv.close();

    NS_LOG_INFO("[" << m_name << " stopped]");
}