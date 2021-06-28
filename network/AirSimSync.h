#ifndef INCLUDE_AIRSIMSYNC_H
#define INCLUDE_AIRSIMSYNC_H
// std includes
#include <vector>
#include <string>
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
#include "gcsApp.h"
#include "uavApp.h"

/* ZMQ ports */
// AIRSIM -> NS (For each application)
#define AIRSIM2NS_UAV_PORT_START (6000)
#define AIRSIM2NS_GCS_PORT_START (4998)
// Ctrl sync ZMQ port
#define NS2AIRSIM_CTRL_PORT (8000)
#define AIRSIM2NS_CTRL_PORT (8001)
// UAV,GCS -> (Pub-Sub) -> Router
#define NS2ROUTER_PORT (9000)


/* NS ports */
// Starting port sequence used by each application to connect to others
#define CONN_PORT_START (3000)
// Starting port sequence used by each application to listen to conn
#define LISTEN_PORT_START (4000)
#define CONG_PORT_START (CONN_PORT_START)

// Start time
#define GCS_APP_START_TIME (0.1)
#define UAV_APP_START_TIME (0.2)
#define CONG_APP_START_TIME (UAV_APP_START_TIME)

using namespace std;

struct NetConfig
{
    float updateGranularity;
    int segmentSize;
    int numOfCong;
    float congRate;
    float congX, congY, congRho;
    std::vector<string> uavsName;
    std::vector< std::vector<float> > initEnbApPos;
    
    int nRbs;
    uint TcpSndBufSize; // was 429496729
    uint TcpRcvBufSize; // was 429496729
    uint CqiTimerThreshold;
    double LteTxPower;
    std::string p2pDataRate = "10Gb/s";
    uint p2pMtu;
    double p2pDelay;
    int useWifi;
    
    int isMainLogEnabled;
    int isGcsLogEnabled;
    int isUavLogEnabled;
    int isCongLogEnabled;
    int isSyncLogEnabled;

};

std::istream& operator>>(istream & is, NetConfig &config);
std::ostream& operator<<(ostream & os, const NetConfig &config);

class AirSimSync
{
public:
    AirSimSync(zmq::context_t &context);
    ~AirSimSync();
    void readNetConfigFromAirSim(NetConfig &config);
    void setUavMobility(std::map< std::string, Ptr<ConstantPositionMobilityModel> > uavsMobility)
    {
        this->m_uavsMobility = uavsMobility;
    }
    void startAirSim();
    void takeTurn(Ptr<GcsApp> &gcsApp, std::vector< Ptr<UavApp> > &uavsApp);
private:
    zmq::socket_t zmqRecvSocket, zmqSendSocket;
    float updateGranularity;
    EventId event;
    bool waitOnAirSim = true;

    void mobilityUpdateDirect();
    // use their names to refer to AirSim vehicle key and update mobility directly
    std::map< std::string, Ptr<ConstantPositionMobilityModel> > m_uavsMobility;
};

#endif