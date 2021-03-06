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
    sendAuth(socket);
    socket->SetSendCallback(MakeCallback(&AirSimNAppBase::sendCallback, this));
    NS_LOG_INFO("[NS Time: " << Simulator::Now().GetSeconds() << "], [" << m_name << " accept] from " << from);
}
/* Trigger the next flow or continue the current one */
void AirSimNAppBase::sendCallback(Ptr<Socket> socket, uint32_t txSpace)
{
    triggerFlow(socket, txSpace);
    // NS_LOG_INFO(m_name << " is sending " << txSpace << " bytes");
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
        flowTransfer(name);
    }
    else if(
        m_address2Name.find(from) != m_address2Name.end() &&
        m_address2Name[from].find(CONG_APP_TOKEN) != std::string::npos
    ){ // traffic from congestion app
        // NS_LOG_INFO("[" << m_name << "], recv traffic from " << m_address2Name[from] << ", size " << packet->GetSize());
    }
    else{ // don't read, we have known who it is, forward to py application 
        std::stringstream ss;
        std::string s;

        ss << m_address2Name[from] << " " << m_name << " " << FLOWOP_RECV << " " << packet->GetSize();
        s = ss.str();
        zmq::message_t message(s.size());
        memcpy((uint8_t*)(message.data()), s.data(), s.size());
        m_zmqSocketSend.send(message, zmq::send_flags::dontwait);
        NS_LOG_INFO("[NS Time: " << Simulator::Now().GetSeconds() << "], [" << m_name  << " recv] from-\"" << m_address2Name[from] << "\", " << packet->GetSize() << " bytes");
    }
}
/* auto auth (for symmetry between GCS and UAV) */
void AirSimNAppBase::connectSuccCallback(Ptr<Socket> socket)
{
    sendAuth(socket);
    socket->SetSendCallback(MakeCallback(&AirSimNAppBase::sendCallback, this));
}
/* simply report a FATAL ERROR */
void AirSimNAppBase::connectFailCallback(Ptr<Socket> socket)
{
    NS_FATAL_ERROR("[" << m_name << "], connect Fail");
}
/* simply log*/
void AirSimNAppBase::closeNormCallback(Ptr<Socket> socket)
{
    for(auto it:m_name2Socket){
        if(it.second == socket){
            NS_LOG_INFO("[" << m_name << "], connection to " << it.first << "Closed");
        }
    }
}
/* report which connection has close error (raise FATAL ERROR) */
void AirSimNAppBase::closeErrorCallback(Ptr<Socket> socket)
{
    for(auto it:m_name2Socket){
        if(it.second == socket){
            NS_FATAL_ERROR("[" << m_name << "], connection to " << it.first << "Close Error");
        }
    }
}
/* send auth */
void AirSimNAppBase::sendAuth(Ptr<Socket> socket)
{
    Ptr<Packet> packet = Create<Packet>((const uint8_t*)(m_name.data()), m_name.size());

    NS_LOG_INFO("My name is " << m_name);
    if(socket->Send(packet) < 0){
        NS_FATAL_ERROR(m_name << " sends its name Error");
    }
    else{
        // NS_LOG_INFO(m_name << " sends its name to " << m_socket2Name[socket]);
    }
}

/*
Either keep transmitting the current flow or auto trigger the next one
<src(this)> <dst> "SEND" <size> <fid>
*/
void AirSimNAppBase::triggerFlow(Ptr<Socket> socket, uint32_t txSpace)
{
    // NS_LOG_INFO(m_name << ": flow left: " << m_flows2Dst[socket].size());
    // clear completed flows if any
    while(!m_flows2Dst[socket].empty() && m_flows[m_flows2Dst[socket].front()].left <= 0){
        int finished = m_flows2Dst[socket].front();
        int erased;
        NS_LOG_INFO("[" << m_name << "], finished " << finished);
        erased = m_flows.erase(finished);
        m_flows2Dst[socket].pop();
    }
    if(!m_flows2Dst[socket].empty() && txSpace > 0){
        int fid = m_flows2Dst[socket].front();
        int size = std::min(txSpace, m_flows[fid].left);
        Ptr<Packet> packet = Create<Packet>(size);
        
        int res = socket->Send(packet);
        if(res >= 0){
            m_flows[fid].left -= size;
        }

        // report to py app
        std::stringstream ss;
        std::string s;
        ss << m_name << " " << m_socket2Name[socket] << " " << FLOWOP_SEND << " " << packet->GetSize() << " " << m_flows2Dst[socket].front();
        s = ss.str();
        zmq::message_t message(s.size());

        memcpy((uint8_t*)(message.data()), s.data(), s.size());
        m_zmqSocketSend.send(message, zmq::send_flags::dontwait);
        NS_LOG_INFO("[NS Time: " << Simulator::Now().GetSeconds() << "], [" << m_name  << " send] to " << m_socket2Name[socket] << ", " << size << " bytes");
    }
}

/*
to transfer the buffer flow to dst 
called when request comes first than auth from dst
then the flows are transfer to another place
buffer cleared
*/
void AirSimNAppBase::flowTransfer(std::string dst)
{
    Ptr<Socket> socket = m_name2Socket[dst];
    NS_LOG_INFO("[" << m_name << "], Flow transfer with dst=" << dst);
    while(!m_pendingFlow[dst].empty()){
        int fid = m_pendingFlow[dst].front();
        m_pendingFlow[dst].pop();
        m_flows2Dst[socket].push(fid);
    }
    triggerFlow(socket, socket->GetTxAvailable());
}
/*
Process request from py app
<flowid> "SEND" <size> <dst>
<flowid> "STOP" 
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
        std::string op;
        
        ss >> fid >> op;
        NS_LOG_INFO("[" << m_name << "], req:\"" << message.to_string() << "\"");
        if(op == FLOWOP_SEND){
            int size;
            std::string dst;
            Ptr<Socket> socket;

            ss >> size >> dst;
            flow::Flow f(fid, size, dst);

            // dst is known, safe
            if(m_name2Socket.find(dst) != m_name2Socket.end()){
                socket = m_name2Socket[dst];
                m_flows[fid] = f;
                if(m_flows2Dst.find(socket) == m_flows2Dst.end()){
                    m_flows2Dst[socket] = std::queue<int>();
                }
                m_flows2Dst[socket].push(fid);
                triggerFlow(socket, socket->GetTxAvailable());
            }
            else{ // keep queuing to pending flow
                if(m_pendingFlow.find(dst) == m_pendingFlow.end()){
                    m_pendingFlow[dst] = queue<int>();
                }
                m_pendingFlow[dst].push(fid);
                NS_LOG_INFO("[" << m_name << "], queue flow " << fid);
            }
        }
        // else if(op == FLOWOP_STOP){ // a flow can be stopped if it was not started yet
        //     int succ = 0;
        //     int left = -1;
        //     std::string dst = "None";
        //     if(m_flows.find(fid) != m_flows.end()){
        //         left = m_flows[fid].left;
        //         dst = m_flows[fid].dst;
        //         if(m_flows2Dst[m_name2Socket[dst]].front() != fid){ // not started
        //             succ = 1;
        //             m_flows[fid].left = -1; // set to < 0 means canceled if sendCallback may race with this (but I think it won't)
        //         }
        //     }
        //     std::stringstream sss;
        //     sss << m_name << " " << dst << " " << op << " " << succ << " " << fid << " " << left;
        //     std::string s = sss.str();
        //     NS_LOG_INFO("[" << m_name << "], " << s);
        //     zmq::message_t message(s.size());
        //     memcpy((uint8_t*)(message.data()), s.data(), s.size());
        //     m_zmqSocketSend.send(message, zmq::send_flags::dontwait);
        // }
        else{
            NS_FATAL_ERROR("op:\"" << op << "\" not handled");
        }
        message.rebuild();
        res = m_zmqSocketRecv.recv(message, zmq::recv_flags::dontwait);
    }
}
/* NS close routine */
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