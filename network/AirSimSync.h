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
// externs
extern zmq::context_t context;


#define NS2AIRSIM_PORT_START (5000)
#define AIRSIM2NS_PORT_START (6000)
#define NS2AIRSIM_GCS_PORT (4999)
#define AIRSIM2NS_GCS_PORT (4998)

#define UAV_PORT_START (3000)
#define GCS_PORT_START (4000)
#define CONG_PORT_START (UAV_PORT_START)

#define NS2AIRSIM_CTRL_PORT (8000)
#define AIRSIM2NS_CTRL_PORT (8001)

#define GCS_APP_START_TIME (0.1)
#define UAV_APP_START_TIME (0.2)
#define CONG_APP_START_TIME (UAV_APP_START_TIME)

#define CLEAN_UP_TIME (1.0)

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
    
    int nRbs; // see https://i.imgur.com/q55uR8T.png
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

class AirSimSync
{
public:
    AirSimSync(zmq::context_t &context);
    ~AirSimSync();
    void readNetConfigFromAirSim(NetConfig &config);
    void startAirSim();
    void takeTurn(Ptr<GcsApp> &gcsApp, std::vector< Ptr<UavApp> > &uavsApp);
private:
    zmq::socket_t zmqRecvSocket, zmqSendSocket;
    float updateGranularity;
    EventId event;
    bool waitOnAirSim = true;
};
std::istream& operator>>(istream & is, NetConfig &config);
std::ostream& operator<<(ostream & os, const NetConfig &config);

#endif