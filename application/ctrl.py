import setup_path
import airsim
import threading
import re
import zmq
import time
import sys
import heapq
import json
import math
# Theses vars correspond to AirSimSync.h
NS2AIRSIM_PORT_START = 5000
AIRSIM2NS_PORT_START = 6000
NS2AIRSIM_GCS_PORT = 4999
AIRSIM2NS_GCS_PORT = 4998
NS2AIRSIM_CTRL_PORT = 8000
AIRSIM2NS_CTRL_PORT = 8001
GCS_APP_START_TIME = 0.1
UAV_APP_START_TIME = 0.2

'''
Remember to reopen AirSim if non-ns3 part is modified

default settings.json
{
	"SeeDocsAt": "https://github.com/Microsoft/AirSim/blob/master/docs/settings.md",
	"SettingsVersion": 1.2,
	"SimMode": "Multirotor",
	"ClockSpeed": 1,
	
	"Vehicles": {
		"A": {
		  "VehicleType": "SimpleFlight",
		  "X": 0, "Y": 0, "Z": 0
		},
		"B": {
		"VehicleType": "SimpleFlight",
		"X": 1, "Y": 0, "Z": 0
		}
    },

	"updateGranularity": 0.01,
            
	"segmentSize": 1448,
	"numOfCong": 0,
	"congRate": 1.0,
	"congArea": [0, 0, 10],
	
	"initEnbApPos": [
		[0, 0, 0]
	],

	"nRbs": 6,
	"TcpSndBufSize": 71680,
	"TcpRcvBufSize": 71680,
	"CqiTimerThreshold": 10,
	"LteTxPower": 0,
	"p2pDataRate": "10Gb/s",
	"p2pMtu": 1500,
	"p2pDelay": 1e-3,
	"useWifi": 1,
	
	"isMainLogEnabled": 1,
	"isGcsLogEnabled": 1,
	"isUavLogEnabled": 1,
	"isCongLogEnabled": 0,
	"isSyncLogEnabled": 0,

	"endTime":5.0
}
'''
class Ctrl(threading.Thread):
    '''
    Usage:
    ctrlThread = ctrl.Ctrl(AIRSIM2NS_CTRL_PORT, NS2AIRSIM_CTRL_PORT, zmq_context)
    netConfig = ctrlThread.sendNetConfig(json_path)
    ctrlThread.waitForSyncStart()
    ctrlThread.join()
    '''
    endTime = math.inf
    mutex = threading.Lock()
    simTime = 0
    lastTimestamp = time.time()
    isRunning = True
    suspended = []
    netConfig = {}
    sn = 0 # serial number

    def __init__(self, context, verbose=False, **kwargs):
        '''
        Control the pace of simulation
        Note that there should be only 1 instance of this class
        since some of the feature is static
        '''
        zmqSendPort = AIRSIM2NS_CTRL_PORT
        zmqRecvPort = NS2AIRSIM_CTRL_PORT
        
        NS2AIRSIM_CTRL_PORT
        threading.Thread.__init__(self)
        self.zmqRecvSocket = context.socket(zmq.PULL)
        self.zmqRecvSocket.connect(f'tcp://localhost:{zmqRecvPort}')

        self.zmqSendSocket = context.socket(zmq.PUSH)
        self.zmqSendSocket.bind(f'tcp://*:{zmqSendPort}')
        self.client = airsim.MultirotorClient()
        self.client.confirmConnection()
        self.client.simRunConsoleCommand('stat fps')
        
        self.verbose = verbose
    
    @staticmethod
    def Wait(delay):
        '''
        Let the calling thread wait the specified amount of time
        Reutrn immediately if this thread is not running
        '''
        with Ctrl.mutex:
            isRunning = Ctrl.isRunning
            if isRunning is True:
                cond = threading.Condition()
                heapq.heappush(Ctrl.suspended, (Ctrl.simTime + delay, Ctrl.sn, cond))
                Ctrl.sn += 1
        if isRunning is True:
            cond.acquire()
            cond.wait()
            cond.release()
    @staticmethod
    def NotifyWait():
        '''
        internal use only
        notfiy the waiting thread if delay is expired
        notify every waiting if simulation is not running
        '''
        with Ctrl.mutex:
            if Ctrl.isRunning: # maintain delay
                while len(Ctrl.suspended) > 0 and Ctrl.simTime >= Ctrl.suspended[0][0]:
                    t, sn, cond = Ctrl.suspended[0]
                    cond.acquire()
                    cond.notify()
                    cond.release()
                    heapq.heappop(Ctrl.suspended)
            else: # release all pending threads
                while len(Ctrl.suspended) > 0:
                    t, sn, cond = heapq.heappop(Ctrl.suspended)
                    cond.acquire()
                    cond.notify()
                    cond.release()
    @staticmethod
    def ShouldContinue():
        '''
        All threads should call this to check whether simulation is still running
        '''
        with Ctrl.mutex:
            isRunning = Ctrl.isRunning
        return isRunning and Ctrl.GetSimTime() < Ctrl.GetEndTime()
   
    @staticmethod
    def SetEndTime(endTime):
        with Ctrl.mutex:
            Ctrl.endTime = endTime
    @staticmethod
    def GetEndTime():
        with Ctrl.mutex:
            temp = Ctrl.endTime
        return temp
    @staticmethod
    def GetSimTime():
        '''
        Retreive the clock maintained by this thread
        '''
        with Ctrl.mutex:
            temp = Ctrl.simTime
        return temp
    @staticmethod
    def GetFineTime():
        '''
        get continuous version of time
        '''
        with Ctrl.mutex:
            temp = Ctrl.simTime + (time.time() - Ctrl.lastTimestamp)
        return temp
    
    def waitForSyncStart(self):
        '''
        to synchronize start
        Corresponds to nsAirSimBegin() in AirSimSync.cc
        '''
        self.zmqRecvSocket.recv()
        self.client.reset()
        self.client.simPause(False)
        # static member init
        with Ctrl.mutex:
            Ctrl.simTime = 0
            Ctrl.lastTimestamp = time.time()
    @staticmethod
    def GetNetConfig():
        with Ctrl.mutex:
            ret = Ctrl.netConfig
        return ret
    def sendNetConfig(self, json_path):
        '''
        send network configuration to and config ns
        '''
        netConfig = {
            'updateGranularity': 0.01,
            
            'segmentSize': 1448,
            'numOfCong': 1.0,
            'congRate': 1.0,
            'congArea': [0, 0, 10],
            
            #  uav names parsing
            'uavsName': [],
            # enb position parsing
            'initEnbApPos': [
                [0, 0, 0]
            ],

            "nRbs": 6, # see https://i.imgur.com/q55uR8T.png
            "TcpSndBufSize": 71680,
            "TcpRcvBufSize": 71680, # as long as it is larger than one picture
            "CqiTimerThreshold": 10,
            "LteTxPower": 0,
            "p2pDataRate": "10Gb/s",
            "p2pMtu": 1500,
            "p2pDelay": 1e-3,
            "useWifi": 0,
            
            "isMainLogEnabled": 1,
            "isGcsLogEnabled": 1,
            "isUavLogEnabled": 1,
            "isCongLogEnabled": 0,
            "isSyncLogEnabled": 0,

            # var not sent
            "endTime":math.inf
        }
        # overwrite default settings
        with open(json_path) as f:
            print(f'Using settings.json in {json_path}')
            settings = json.load(f)
            for key in netConfig:
                if key in settings:
                    netConfig[key] = settings[key]
            netConfig['uavsName'] = [key for key in settings['Vehicles']]
        print('========== Parsed config ==========')
        print(netConfig)
        print('========== ============= ==========')

        # preparing for sending to NS

        s = ''
        s += f'{netConfig["updateGranularity"]} {netConfig["segmentSize"]} '
        s += f'{netConfig["numOfCong"]} {netConfig["congRate"]} {netConfig["congArea"][0]} {netConfig["congArea"][1]} {netConfig["congArea"][2]} '
        
        # UAVs
        s += f'{len(netConfig["uavsName"])} '
        for name in netConfig["uavsName"]:
            s += f'{name} '
        # Enbs
        s += f'{len(netConfig["initEnbApPos"])} '
        for pos in netConfig["initEnbApPos"]:
            s += f'{pos[0]} {pos[1]} {pos[2]} '
        
        s += f'{netConfig["nRbs"]} {netConfig["TcpSndBufSize"]} {netConfig["TcpRcvBufSize"]} {netConfig["CqiTimerThreshold"]} '
        s += f'{netConfig["LteTxPower"]} {netConfig["p2pDataRate"]} {netConfig["p2pMtu"]} {netConfig["p2pDelay"]} '
        
        s += f'{netConfig["useWifi"]} '
        s += f'{netConfig["isMainLogEnabled"]} {netConfig["isGcsLogEnabled"]} {netConfig["isUavLogEnabled"]} {netConfig["isCongLogEnabled"]} {netConfig["isSyncLogEnabled"]} '
        
        self.zmqSendSocket.send_string(s)
        # rm timeout
        # self.zmqRecvSocket.setsockopt(zmq.RCVTIMEO, int(10*1000*netConfig["updateGranularity"]))
        self.netConfig = netConfig
        Ctrl.netConfig = netConfig
        Ctrl.SetEndTime(netConfig["endTime"])
        return netConfig
    def advance(self):
        '''
        advace the simulation by a small step
        '''
        try:
            msg = self.zmqRecvSocket.recv()
            # this will block until resumed
            self.client.simContinueForTime(self.netConfig['updateGranularity'])
            Ctrl.NotifyWait()
            with Ctrl.mutex:
                Ctrl.simTime += self.netConfig['updateGranularity']
                Ctrl.lastTimestamp = time.time()
                self.zmqSendSocket.send_string('')
                if self.verbose:
                    print(f'Time = {Ctrl.simTime}')
        except zmq.ZMQError:
            print('ctrl msg not received')
    def run(self):
        '''
        control and advance the whole simulation
        '''
        while Ctrl.ShouldContinue():
            self.advance()
        with Ctrl.mutex:
            Ctrl.isRunning = False
        self.zmqSendSocket.send_string(f'bye {Ctrl.GetEndTime()}')
        self.NotifyWait()
        