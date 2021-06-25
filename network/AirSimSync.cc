// standard includes
#include <sstream>
// ns3 includes
#include "ns3/core-module.h"
#include "ns3/network-module.h"
#include "ns3/internet-module.h"
#include "ns3/point-to-point-module.h"
#include "ns3/applications-module.h"

#include "ns3/mobility-module.h"
#include "ns3/wifi-module.h"
#include "ns3/ipv4-global-routing-helper.h"
#include "ns3/lte-helper.h"
#include "ns3/epc-helper.h"
#include "ns3/lte-module.h"
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
// custom includes
#include "AirSimSync.h"

using namespace std;
extern NetConfig config;

NS_LOG_COMPONENT_DEFINE("AIRSIM_SYNC");

std::istream& operator>>(istream & is, NetConfig &config)
{
    int numOfUav, numOfEnb;
    is >> config.updateGranularity;
    is >> config.segmentSize >> config.numOfCong >> config.congRate >> config.congX >> config.congY >> config.congRho;
    
    // uav names parsing
    is >> numOfUav;
    config.uavsName = std::vector<std::string>(numOfUav);
    for(int i = 0; i < numOfUav; i++){
        is >> config.uavsName[i];
    }
    // enb position parsing
    is >> numOfEnb;
    config.initEnbApPos = std::vector< std::vector<float> >(numOfEnb, std::vector<float>(3));
    for(int i = 0; i < numOfEnb; i++){
        is >> config.initEnbApPos[i][0] >> config.initEnbApPos[i][1] >> config.initEnbApPos[i][2];
    }

    // net config group
    is >> config.nRbs >> config.TcpSndBufSize >> config.TcpRcvBufSize >> config.CqiTimerThreshold;
    is >> config.LteTxPower >> config.p2pDataRate >> config.p2pMtu >> config.p2pDelay;
    is >> config.useWifi;
    
    is >> config.isMainLogEnabled >> config.isGcsLogEnabled >> config.isUavLogEnabled >> config.isCongLogEnabled >> config.isSyncLogEnabled;

    return is;
}
std::ostream& operator<<(ostream & os, const NetConfig &config)
{
    os << "update granularity: " << config.updateGranularity << endl;
    os << "seg size:" << config.segmentSize << endl;
    os << "numOfCong:" << config.numOfCong << " congRate:" << config.congRate << "congX:" << config.congX << " congY:" << config.congY << " congRho:" << config.congRho  << endl;
    
    // UAV names
    os << "UAV names(" << config.uavsName.size() << "):" << endl;
    for(auto it:config.uavsName){
        os << it << ",";
    }
    os << endl;
    // Enbs
    os << "Enb pos:"  << endl;
    for(int i = 0; i < config.initEnbApPos.size(); i++){
        os << i << "(" << config.initEnbApPos[i][0] << ", " << config.initEnbApPos[i][1] << ", " << config.initEnbApPos[i][2] << ")"  << endl;
    }

    os << "nRbs: " << config.nRbs << ", TcpSndBufSize:" << config.TcpSndBufSize << ", TcpRcvBufSize:" << config.TcpRcvBufSize << endl;
    os << "CqiTimerThreshold: " << config.CqiTimerThreshold << ", LteTxPower: " << config.LteTxPower << ", p2pDataRate:" << config.p2pDataRate << ", p2pMtu: " << config.p2pMtu << ", p2pDelay: " << config.p2pDelay << endl;
    
    os << "useWifi: " << config.useWifi;
    return os;
}

AirSimSync::AirSimSync(zmq::context_t &context): event()
{
    zmqRecvSocket = zmq::socket_t(context, ZMQ_PULL);
    zmqRecvSocket.connect("tcp://localhost:" + to_string(AIRSIM2NS_CTRL_PORT));
    zmqSendSocket = zmq::socket_t(context, ZMQ_PUSH);
    zmqSendSocket.bind("tcp://*:" + to_string(NS2AIRSIM_CTRL_PORT));
}
AirSimSync::~AirSimSync()
{
    zmqRecvSocket.close();
    zmqSendSocket.close();
}

void AirSimSync::readNetConfigFromAirSim(NetConfig &config)
{
    zmq::message_t message;
    zmqRecvSocket.recv(message, zmq::recv_flags::none);
    std::string s(static_cast<char*>(message.data()), message.size());
    std::istringstream ss(s);
    
    ss >> config;
    updateGranularity = config.updateGranularity;
    // rm timeout
    // zmqRecvSocket.setsockopt(ZMQ_RCVTIMEO, (int)(1000*1000*config.updateGranularity));
}
void AirSimSync::startAirSim()
{
    zmq::message_t ntf(1);
    // notify AirSim
    zmqSendSocket.send(ntf, zmq::send_flags::none);
}
void AirSimSync::takeTurn(Ptr<GcsApp> &gcsApp, std::vector< Ptr<UavApp> > &uavsApp)
{
    float now = Simulator::Now().GetSeconds();
    zmq::message_t message;
    zmq::recv_result_t res;
    zmq::message_t ntf(1);
    
    // notify AirSim
    zmqSendSocket.send(ntf, zmq::send_flags::dontwait);
    
    // AirSim's turn at time t
    // block until AirSim sends any (nofitied by AirSim)
    res = zmqRecvSocket.recv(message, zmq::recv_flags::none);
    NS_LOG_INFO("TIME: " << now);
    
    std::string s(static_cast<char*>(message.data()), message.size());
    std::size_t n = s.find("bye");
    // This implied that a hard limit of 10 times updateGranularity for AirSim to run a period
    if((!res.has_value() || res.value() < 0) || (n != std::string::npos)){
        double endTime = 0.0;
        if(event.IsRunning()){
            Simulator::Cancel(event);
        }
        zmqSendSocket.send(ntf, zmq::send_flags::dontwait);
        gcsApp->SetStopTime(Seconds(endTime));
        for(auto &it:uavsApp){
            it->SetStopTime(Seconds(endTime));
        }
        if(n == std::string::npos){
            NS_LOG_INFO("Termination triggered by timeout");
        }
        if(!res.has_value()){
            NS_LOG_INFO("Termination triggered by has_value() is false");
        }
        if(res.has_value() && res.value() < 0){
            NS_LOG_INFO("Termination triggered by res value " << res.value());
        }
        Simulator::Stop(Seconds(endTime));
    }
    
    // ns' turn at time t, AirSim at time t + 1
    // packet send
    gcsApp->mobilityUpdateDirect();
    if(gcsApp){
        gcsApp->scheduleTx();
    }
    for(int i = 0; i < uavsApp.size(); i++){
        uavsApp[i]->scheduleTx();
    }

    // will fire at time t + 1
    Time tNext(Seconds(updateGranularity));
    event = Simulator::Schedule(tNext, &AirSimSync::takeTurn, this, gcsApp, uavsApp);
}
