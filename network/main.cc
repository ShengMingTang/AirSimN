// std includes
#include <vector>
#include <ctime>
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
#include "ns3/flow-monitor-helper.h"
#include "ns3/ipv4-flow-probe.h"
// zmq includes
#include <zmq.hpp>
// custom includes
#include "gcsApp.h"
#include "uavApp.h"
#include "congApp.h"
#include "AirSimSync.h"

// LTE topology (useWifi=0)
// 
//  * = Enb  G=GCS  u=UAV
// 
//    ----------* ==========
//   /          * |        |
//  /  (7.0.0.0)* |      PGW (.2) --- 1.0.0.0 ---(.1) G
// u   u -------* ==========
// 
//   | E-UTRAN  | |   EPC  | | GCS backend |

// Wifi topology (useWifi=1)
// 
//  * = AP  G=GCS  u=UAV
// 
//   Wifi 10.1.1.0
// *(0)---*(1)---------*(2)
// |        \           \
// G         \           \
//            u(0)        u(1)

using namespace std;
using namespace ns3;

NS_LOG_COMPONENT_DEFINE ("NS_AIRSIM");

NetConfig config;

int main(int argc, char *argv[])
{
  // local vars
  zmq::context_t context(1);
  srand (static_cast <unsigned> (time(0)));

  CommandLine cmd (__FILE__);
  cmd.Parse (argc, argv);

  AirSimSync sync(context);
  sync.readNetConfigFromAirSim(config);

  if(config.isMainLogEnabled) {LogComponentEnable("NS_AIRSIM", LOG_LEVEL_INFO);}
  if(config.isGcsLogEnabled) {LogComponentEnable("GcsApp", LOG_LEVEL_INFO);}
  if(config.isUavLogEnabled) {LogComponentEnable("UavApp", LOG_LEVEL_INFO);}
  if(config.isCongLogEnabled) {LogComponentEnable("CongApp", LOG_LEVEL_INFO);}
  if(config.isSyncLogEnabled) {LogComponentEnable("AIRSIM_SYNC", LOG_LEVEL_INFO);}

  NS_LOG_INFO("Use config:" << config);

  if(config.initEnbApPos.size() == 0){
    NS_FATAL_ERROR("initEnbApPos should have at least length 1 but got " << config.initEnbApPos.size());
  }

  Time::SetResolution(Time::NS);
  
  // ==========================================================================
  // Config LTE
  Config::SetDefault ("ns3::LteSpectrumPhy::CtrlErrorModelEnabled", BooleanValue (false));
  Config::SetDefault ("ns3::LteSpectrumPhy::DataErrorModelEnabled", BooleanValue (true));
  Config::SetDefault ("ns3::PfFfMacScheduler::HarqEnabled", BooleanValue (false));
  Config::SetDefault ("ns3::PfFfMacScheduler::CqiTimerThreshold", UintegerValue (config.CqiTimerThreshold));
  Config::SetDefault ("ns3::LteEnbRrc::EpsBearerToRlcMapping",EnumValue(LteEnbRrc::RLC_AM_ALWAYS));
  Config::SetDefault ("ns3::LteEnbNetDevice::UlBandwidth", UintegerValue(config.nRbs));
  Config::SetDefault ("ns3::LteEnbNetDevice::DlBandwidth", UintegerValue(config.nRbs));
  Config::SetDefault ("ns3::LteUePhy::EnableUplinkPowerControl", BooleanValue (false));
  Config::SetDefault ("ns3::LteUePhy::TxPower", DoubleValue(config.LteTxPower));
  // Config TCP socket
  // https://www.nsnam.org/doxygen/classns3_1_1_tcp_socket.html
  Config::SetDefault("ns3::TcpSocket::SegmentSize", UintegerValue(config.segmentSize));
  Config::SetDefault("ns3::TcpSocket::SndBufSize", UintegerValue(config.TcpSndBufSize));
  Config::SetDefault("ns3::TcpSocket::RcvBufSize", UintegerValue(config.TcpRcvBufSize));

  // Packet level settings
  ns3::Packet::EnablePrinting();

  // ==========================================================================
  // Node containers
  NodeContainer uavNodes;
  NodeContainer gcsNodes; // GCS contains only 1 node
  NodeContainer enbApNodes; // Enb (LTE) | AP (Wifi)
  NodeContainer congNodes;
  Ptr<Node> gcsNode;
  Ptr<Node> pgwNode; // LTE only
  Ptr<Node> sgwNode; // LTE only

  NS_LOG_INFO("Creating Nodes");
  uavNodes.Create(config.uavsName.size());
  gcsNodes.Create(1);
  gcsNode = gcsNodes.Get (0); // GCS (later be installed with pgw) | 
  enbApNodes.Create(config.initEnbApPos.size()); // position shared
  congNodes.Create(config.numOfCong);
  
  // ==========================================================================
  // mobility (must set before UE devices attach)
  MobilityHelper mobilityUav;
  MobilityHelper mobilityGcs;
  MobilityHelper mobilityEnbAp;
  MobilityHelper mobilityCong;
  Ptr<ListPositionAllocator> initPosUavAlloc = CreateObject<ListPositionAllocator>();
  Ptr<ListPositionAllocator> initPosGcsAlloc = CreateObject<ListPositionAllocator>();
  Ptr<ListPositionAllocator> initPosEnbApAlloc = CreateObject<ListPositionAllocator> ();
  Ptr<ListPositionAllocator> initPosCongAlloc = CreateObject<ListPositionAllocator>();
  
  NS_LOG_INFO("Adding mobility");
  // UAV, Initial position is left to AirSim, update in the start of an application
  for(uint32_t i = 0; i < uavNodes.GetN(); i++){
    initPosUavAlloc->Add(Vector(0, 0, 0));
  }
  mobilityUav.SetMobilityModel("ns3::ConstantPositionMobilityModel");
  mobilityUav.SetPositionAllocator(initPosUavAlloc);
  mobilityUav.Install(uavNodes); // allocate corresponding indexed initial position

  // GCS
  // it has mobility only if in Wifi mode
  if(config.useWifi){
    initPosGcsAlloc->Add(Vector(config.initEnbApPos[0][0], config.initEnbApPos[0][1], config.initEnbApPos[0][2]));
    mobilityGcs.SetMobilityModel ("ns3::ConstantPositionMobilityModel");
    mobilityGcs.SetPositionAllocator(initPosGcsAlloc);
    mobilityGcs.Install (gcsNode);
  }

  // EnbAp
  for(int i = 0; i < enbApNodes.GetN(); i++){
    initPosEnbApAlloc->Add(Vector(config.initEnbApPos[i][0], config.initEnbApPos[i][1], config.initEnbApPos[i][2]));
  }
  mobilityEnbAp.SetMobilityModel ("ns3::ConstantPositionMobilityModel");
  mobilityEnbAp.SetPositionAllocator(initPosEnbApAlloc);
  mobilityEnbAp.Install (enbApNodes);
  
  // Cong
  mobilityCong.SetMobilityModel ("ns3::ConstantPositionMobilityModel");
  mobilityCong.SetPositionAllocator("ns3::UniformDiscPositionAllocator",
					"rho", DoubleValue(config.congRho),
					"X", DoubleValue(config.congX),
					"Y", DoubleValue(config.congY));
  mobilityCong.Install(congNodes);

  // ==========================================================================
  // Internet stack
  InternetStackHelper stack;
  NS_LOG_INFO("Install Internet stacks");
  stack.Install(uavNodes);
  // Enb don't need protocol stack
  if(config.useWifi) {stack.Install(enbApNodes);}
  stack.Install(gcsNode);
  stack.Install(congNodes);

  // ==========================================================================
  // Netdevice containers
  NetDeviceContainer uavDevices;
  NetDeviceContainer gcsDevices; // GCS + PGW (LTE) | GCS + first AP (Wifi)
  NetDeviceContainer enbApDevices;
  NetDeviceContainer congDevices;
  /* LTE */
  Ptr<LteHelper> lteHelper = CreateObject<LteHelper>();
  Ptr<PointToPointEpcHelper> epcHelper = CreateObject<PointToPointEpcHelper>();
  PointToPointHelper p2ph; // gcsNode(GCS) - pgw (LTE) |  
  
  
  /* Wifi */
  YansWifiChannelHelper channel = YansWifiChannelHelper::Default ();
  YansWifiPhyHelper phy = YansWifiPhyHelper::Default ();
  WifiHelper wifi;
  WifiMacHelper mac;
  Ssid ssid = Ssid ("ns-3-ssid");
  
  p2ph.SetDeviceAttribute ("DataRate", DataRateValue (DataRate (config.p2pDataRate.c_str())));
  p2ph.SetDeviceAttribute ("Mtu", UintegerValue (config.p2pMtu));
  p2ph.SetChannelAttribute ("Delay", TimeValue (Seconds (config.p2pDelay)));

  if(!config.useWifi){ /* LTE */
    NS_LOG_INFO("Setup LTE helper");
    lteHelper->SetHandoverAlgorithmType ("ns3::NoOpHandoverAlgorithm"); // disable automatic handover
    lteHelper->SetAttribute ("PathlossModel", StringValue ("ns3::FriisPropagationLossModel"));

    NS_LOG_INFO("Setup EPC helper");
    lteHelper->SetEpcHelper(epcHelper);
    pgwNode = epcHelper->GetPgwNode();
    sgwNode = epcHelper->GetSgwNode(); // this is not used in our case

    // @@ Enb device must be installed before UE devices are installed
    enbApDevices = lteHelper->InstallEnbDevice(enbApNodes);
    
    uavDevices = lteHelper->InstallUeDevice(uavNodes);
    gcsDevices = p2ph.Install(gcsNode, pgwNode);
    congDevices = lteHelper->InstallUeDevice(congNodes);
  }
  else{ /* Wifi */
    NS_LOG_INFO("Setup Wifi devices");
    phy.SetChannel (channel.Create ());
    wifi.SetRemoteStationManager ("ns3::AarfWifiManager");
    mac.SetType ("ns3::StaWifiMac",
                 "Ssid", SsidValue (ssid),
                 "ActiveProbing", BooleanValue (false));
    uavDevices = wifi.Install(phy, mac, uavNodes);
    gcsDevices = wifi.Install(phy, mac, gcsNodes);
    congDevices = wifi.Install(phy, mac, congNodes);
   
    mac.SetType ("ns3::ApWifiMac",
               "Ssid", SsidValue (ssid));
    enbApDevices = wifi.Install(phy, mac, enbApNodes);

  }
  
  // ==========================================================================
  // Ipv4 address
  Ipv4AddressHelper ipv4h;

  Ipv4InterfaceContainer uavIpfaces;
  Ipv4InterfaceContainer gcsIpfaces; // GCS only 
  Ipv4InterfaceContainer enbApIpfaces;
  Ipv4InterfaceContainer congIpfaces;

  /* LTE */
  Ipv4StaticRoutingHelper ipv4RoutingHelper;
  Ptr<Ipv4StaticRouting> gcsStaticRouting;

  if(!config.useWifi){ /* LTE */
    NS_LOG_INFO("Assign UAV interfaces");
    // UAV
    // uavIpfaces = epcHelper->AssignUeIpv4Address(uavDevices);
    for(int i = 0; i< uavNodes.GetN(); i++){
      Ptr<Node> uavNode = uavNodes.Get(i);
      Ptr<NetDevice> uavDevice = uavDevices.Get(i);
      uavIpfaces.Add(epcHelper->AssignUeIpv4Address(NetDeviceContainer(uavDevice)));

      // set the default gateway for the uavNode
      Ptr<Ipv4StaticRouting> uavStaticRouting = ipv4RoutingHelper.GetStaticRouting (uavNode->GetObject<Ipv4> ());
      // @@ index 1 ??
      uavStaticRouting->SetDefaultRoute (epcHelper->GetUeDefaultGatewayAddress (), 1);
     
      // @@ what does this mean ?
      lteHelper->ActivateDedicatedEpsBearer (uavDevice, EpsBearer (EpsBearer::NGBR_VIDEO_TCP_DEFAULT), EpcTft::Default ());
    }
    lteHelper->AttachToClosestEnb(uavDevices, enbApDevices);
    
    // GCS
    NS_LOG_INFO("Assign GCS interfaces");
    ipv4h.SetBase ("1.0.0.0", "255.0.0.0");
    gcsIpfaces = ipv4h.Assign(gcsDevices);
    // @@ where does the "7.0.0.0" come from ? and 1 in AddNetworkRouteTo (only has 1 interface ?)
    gcsStaticRouting = ipv4RoutingHelper.GetStaticRouting (gcsNode->GetObject<Ipv4>());
    gcsStaticRouting->AddNetworkRouteTo (Ipv4Address ("7.0.0.0"), Ipv4Mask ("255.0.0.0"), 1);

    // EnbAp
    // don't need to assign address

    // Cong
    NS_LOG_INFO("Assign Cong interfaces");
    congIpfaces = epcHelper->AssignUeIpv4Address(congDevices);
    for (uint32_t i = 0; i < congNodes.GetN (); i++){
      Ptr<Node> congNode = congNodes.Get (i);
      Ptr<NetDevice> congDevice = congDevices.Get(i);
      // set the default gateway for the congNode
      Ptr<Ipv4StaticRouting> congStaticRouting = ipv4RoutingHelper.GetStaticRouting (congNode->GetObject<Ipv4> ());
      // @@ index 1 ??
      congStaticRouting->SetDefaultRoute (epcHelper->GetUeDefaultGatewayAddress (), 1);

      // @@ what does this mean ?
      lteHelper->ActivateDedicatedEpsBearer (congDevice, EpsBearer (EpsBearer::NGBR_VIDEO_TCP_DEFAULT), EpcTft::Default ());
    }
    lteHelper->AttachToClosestEnb(congDevices, enbApDevices);

  }
  else{ /* Wifi */
  NS_LOG_INFO("Assign Wifi IP interfaces");
    ipv4h.SetBase("10.1.1.0", "255.255.255.0");
    // to keep it address in front of uavs'
    gcsIpfaces = ipv4h.Assign(gcsDevices.Get(0));
    uavIpfaces = ipv4h.Assign(uavDevices);
    congIpfaces = ipv4h.Assign(congDevices);
  }

  // ==========================================================================
  // UAV
  std::map<std::string, Ptr<ConstantPositionMobilityModel> > uavsMobility;
  std::vector< Ptr<UavApp> > uavsApp;
  // GCS
  Address gcsSinkAddress(InetSocketAddress (gcsIpfaces.GetAddress(0), GCS_PORT_START)); // get the 0th address anyway. GCS + PGW (LTE) | GCS (Wifi)
  Ptr<Socket> gcsTcpSocket = Socket::CreateSocket(gcsNode, TcpSocketFactory::GetTypeId());
  Ptr<GcsApp> gcsApp = CreateObject<GcsApp>();
  // Cong
  std::vector< Ptr<CongApp> > congsApp;

  // Add application to uavNodes
  NS_LOG_INFO("Add UAV app");
  for(int i = 0; i < uavNodes.GetN(); i++){  
    // GCS -> UAV (sink)
    uint16_t uavPort = UAV_PORT_START;
    Ptr<Node> uav = uavNodes.Get(i);
    Ipv4Address uavAddress = uavIpfaces.GetAddress(i);
    Ptr<Socket> uavTcpSocket = Socket::CreateSocket(uavNodes.Get(i), TcpSocketFactory::GetTypeId());
    Address uavMyAddress(InetSocketAddress(uavAddress, uavPort));
    Ptr<UavApp> app = CreateObject<UavApp>();
    
    uavNodes.Get(i)->AddApplication(app);
    app->Setup(context, uavTcpSocket, uavMyAddress, gcsSinkAddress,
      AIRSIM2NS_PORT_START + i, NS2AIRSIM_PORT_START + i, config.uavsName[i]
    );
    app->SetStartTime(Seconds(UAV_APP_START_TIME));
    app->SetStopTime(Simulator::GetMaximumSimulationTime());

    uavsMobility[config.uavsName[i]] = uavNodes.Get(i)->GetObject<ConstantPositionMobilityModel>();    
    uavsApp.push_back(app);
  }

  // Add application to gcsNode
  NS_LOG_INFO("Add GCS app");
  gcsNode->AddApplication(gcsApp);
  gcsApp->Setup(context, gcsTcpSocket, InetSocketAddress(Ipv4Address::GetAny(), GCS_PORT_START), 
    uavsMobility,
    AIRSIM2NS_GCS_PORT , NS2AIRSIM_GCS_PORT
  );
  gcsApp->SetStartTime(Seconds(GCS_APP_START_TIME));
  gcsApp->SetStopTime(Simulator::GetMaximumSimulationTime());
  
  // Add application to cong node
  NS_LOG_INFO("Add Cong app");
  for(int i = 0; i < congNodes.GetN(); i++){  
    uint16_t congPort = CONG_PORT_START; // use the same port as uav does
    Ptr<Node> cong = congNodes.Get(i);
    Ipv4Address congAddress = congIpfaces.GetAddress(i);
    Ptr<Socket> congTcpSocket = Socket::CreateSocket(congNodes.Get(i), TcpSocketFactory::GetTypeId());
    Address congMyAddress(InetSocketAddress(Ipv4Address::GetAny(), congPort));
    Ptr<CongApp> app = CreateObject<CongApp>();
    std::string name("anoy");

    name += to_string(i);    
    congNodes.Get(i)->AddApplication(app);
    app->Setup(congTcpSocket, congMyAddress, gcsSinkAddress,
      config.congRate, name
    );
    app->SetStartTime(Seconds(CONG_APP_START_TIME));
    app->SetStopTime(Simulator::GetMaximumSimulationTime());

    congsApp.push_back(app);
  }

  // ==========================================================================
  // Monitor
  FlowMonitorHelper flowmon;
  Ptr<FlowMonitor> uavMonitor = flowmon.Install(uavNodes.Get(0));
  Ptr<FlowMonitor> gcsMonitor = flowmon.Install(gcsNode);

  // ==========================================================================
  // Run
  sync.startAirSim();
  Simulator::ScheduleNow(&AirSimSync::takeTurn, &sync, gcsApp, uavsApp);
  // Simulator::Stop(Seconds(1.99));
  Simulator::Run();
  
  // ==========================================================================
  // Report
  NS_LOG_INFO("UAV monitor:");
  uavMonitor->CheckForLostPackets ();
  Ptr<Ipv4FlowClassifier> uavClassifier = DynamicCast<Ipv4FlowClassifier> (flowmon.GetClassifier ());
  FlowMonitor::FlowStatsContainer uavStats = uavMonitor->GetFlowStats ();
  for (std::map<FlowId, FlowMonitor::FlowStats>::const_iterator i = uavStats.begin (); i != uavStats.end (); ++i){
    Ipv4FlowClassifier::FiveTuple t = uavClassifier->FindFlow (i->first);
    std::cout << "source=" << t.sourceAddress << ", dest=" << t.destinationAddress << " TxBytes= " << i->second.txBytes << ", throughput= "<< i->second.txBytes * 8.0 / (i->second.timeLastTxPacket.GetSeconds() - i->second.timeFirstTxPacket.GetSeconds()+0.001) / 1000 / 1000  << " Mbps"  << endl;
    std::cout << "packet lost=" << i->second.lostPackets << endl;
  }

  NS_LOG_INFO("GCS monitor:");
  gcsMonitor->CheckForLostPackets ();
  Ptr<Ipv4FlowClassifier> gcsClassifier = DynamicCast<Ipv4FlowClassifier> (flowmon.GetClassifier ());
  FlowMonitor::FlowStatsContainer gcsStats = gcsMonitor->GetFlowStats ();
  for (std::map<FlowId, FlowMonitor::FlowStats>::const_iterator i = gcsStats.begin (); i != gcsStats.end (); ++i){
    Ipv4FlowClassifier::FiveTuple t = gcsClassifier->FindFlow (i->first);
    std::cout << "source=" << t.sourceAddress << ", dest=" << t.destinationAddress << " TxBytes= " << i->second.txBytes << ", throughput= "<< i->second.txBytes * 8.0 / (i->second.timeLastTxPacket.GetSeconds() - i->second.timeFirstTxPacket.GetSeconds()+0.001) / 1000 / 1000  << " Mbps"  << endl;
    std::cout << "packet lost=" << i->second.lostPackets << endl;
  }

  // ==========================================================================
  // Clean up
  Simulator::Destroy();
  return 0;
}