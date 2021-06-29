// std includes
#include <cstdlib>
// ns3 includes
#include "ns3/core-module.h"
#include "ns3/network-module.h"
#include "ns3/internet-module.h"
#include "ns3/point-to-point-module.h"
#include "ns3/applications-module.h"
#include "ns3/stats-module.h"
// custom includes
#include "congApp.h"

using namespace std;
using namespace ns3;

NS_LOG_COMPONENT_DEFINE ("CongApp");

CongApp::CongApp(): m_event()
{
    // Todo
}

CongApp::~CongApp()
{
    // Todo
}

TypeId CongApp::GetTypeId(void)
{
    static TypeId tid = TypeId("CongApp")
        .SetParent<Application>()
        .SetGroupName("AirSimN")
        .AddConstructor<CongApp>()
    ;
    return tid;
}

/* Init ns stuff, rPC client connection and zmq socket init, connect */
void CongApp::Setup(Ptr<Socket> socket, Address myAddress, Address peerAddress,
    float congRate, std::string name
)
{
    m_socket = socket;
    m_address = myAddress;
    m_peerAddress = peerAddress;
    m_congRate = congRate;
    m_name = name;
}
void CongApp::connectSuccCallback(Ptr<Socket> socket)
{
    NS_LOG_INFO("My name is " << m_name);
    sendAuth(socket);
    scheduleTx();
}
/* Bind ns sockets and logging*/
void CongApp::StartApplication(void)
{
    // ns socket routines
    m_socket->Bind();
    m_socket->SetConnectCallback(MakeCallback(&CongApp::connectSuccCallback, this), MakeCallback(&CongApp::connectFailCallback, this));
    m_socket->SetCloseCallbacks(MakeCallback(&CongApp::closeNormCallback, this), MakeCallback(&CongApp::closeErrorCallback, this));
    if(m_socket->Connect(m_peerAddress) != 0){
        NS_FATAL_ERROR("[" << m_name << "], connect error");
    }

    m_running = true;
    NS_LOG_INFO("[" << m_name << "], starts");
}
void CongApp::StopApplication (void)
{
    if(m_event.IsRunning()){
        Simulator::Cancel(m_event);
    }
    
    // from parent class
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
void CongApp::scheduleTx(void)
{
    float r; // in [-0.5, 0.5] * 1/m_congRate
    int size = std::min(m_socket->GetTxAvailable(), (uint32_t)CONG_PACKET_SIZE);
    Ptr<Packet> packet = Create<Packet>(size);
    
    m_socket->Send(packet);
    r = static_cast <float> (rand()) / static_cast <float> (RAND_MAX);
    r = (r/2) * (1/m_congRate);
    r = rand() % 2 ? r : -r;
    NS_LOG_INFO("[NS Time: " << Simulator::Now().GetSeconds() << "], [" << m_name  << "], " << size << " bytes");

    Time tNext(Seconds(max((float)1e-3, 1/m_congRate + r)));
    m_event = Simulator::Schedule(tNext, &CongApp::scheduleTx, this);
}