#ifndef INCLUDE_CONGAPP_H
#define INCLUDE_CONGAPP_H

// ns3 includes
#include "ns3/core-module.h"
#include "ns3/network-module.h"
#include "ns3/internet-module.h"
#include "ns3/point-to-point-module.h"
#include "ns3/applications-module.h"
#include "ns3/stats-module.h"
// custom includes
#include "AirSimNAppBase.h"

// Congest at a rate of CONG_PACKET_SIZE * (1/(congRate+small variance))
#define CONG_PACKET_SIZE (1024*5)

using namespace std;
using namespace ns3;

class CongApp: public AirSimNAppBase
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

private:
    virtual void connectSuccCallback(Ptr<Socket> socket);
    virtual void StartApplication (void);
    virtual void StopApplication (void);
    void scheduleTx(void);

    float m_congRate;
    EventId         m_event;
    Address         m_peerAddress;
};

#endif