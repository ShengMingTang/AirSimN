#ifndef INCLUDE_CONGAPP_H
#define INCLUDE_CONGAPP_H

// ns3 includes
#include "ns3/core-module.h"
#include "ns3/network-module.h"
#include "ns3/internet-module.h"
#include "ns3/point-to-point-module.h"
#include "ns3/applications-module.h"
#include "ns3/stats-module.h"

#define CONG_PACKET_SIZE (1024*5)

using namespace std;
using namespace ns3;

class CongApp: public Application
{
public:
    CongApp();
    virtual ~CongApp();

    /**
    * Register this type.
    * \return The TypeId.
    */
    static TypeId GetTypeId(void);
    void Setup(Ptr<Socket> socket, Address myAddress, Address peerAddress,
        float congRate, std::string name
    );

    void scheduleTx(void);
private:
    virtual void StartApplication (void);
    virtual void StopApplication (void);

    void Tx(Ptr<Socket> socket, Ptr<Packet> packet);

    void recvCallback(Ptr<Socket> socket);

    bool m_running;
    std::string m_name;
    float m_congRate;
    // ns stuff
    Ptr<Socket>     m_socket;
    Address         m_address;
    Address         m_peerAddress;
    EventId         m_event;
};

#endif