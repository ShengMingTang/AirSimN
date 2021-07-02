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

# ! CONST VALUE "DON'T MODIFY ANY OF THEN"
# Theses vars correspond to AirSimSync.h
AIRSIM2NS_UAV_PORT_START = 6000
AIRSIM2NS_GCS_PORT_START = 4998
# Ctrl sync ZMQ port
NS2AIRSIM_CTRL_PORT = 8000
AIRSIM2NS_CTRL_PORT = 8001
# UAV,GCS -> (Pub-Sub) -> Router
NS2ROUTER_PORT = 9000

VERBOSE=False # to print sync message
TIME_TEST=False # to tract time spent on ns3 and AirSim 

class Ctrl(threading.Thread):
    '''
    Usage:
    ctrlThread = ctrl.Ctrl(AIRSIM2NS_CTRL_PORT, NS2AIRSIM_CTRL_PORT, zmq_context)
    netConfig = ctrlThread.sendNetConfig(json_path)
    ctrlThread.waitForSyncStart()
    ctrlThread.join()
    
    with Ctrl.Frozen():
        # do some work
    '''
    endTime = math.inf
    mutex = threading.Lock()
    simTime = 0
    isRunning = True
    suspended = []
    netConfig = {}
    sn = 0 # serial number
    freezeSet = set()
    freezeCond = threading.Condition()

    def __init__(self, context, **kwargs):
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
    
    @staticmethod
    def WaitUntil(t, cb=None):
        '''
        Let the calling thread wait until t
        Return immediately if this thread is not running
        @param cb: callback func with empty args
        '''
        with Ctrl.mutex:
            isRunning = Ctrl.isRunning
            tsim = Ctrl.simTime
            sn = Ctrl.sn
            Ctrl.sn += 1
        # suspended
        if isRunning is True and t > tsim:
            cond = threading.Condition()
            with Ctrl.mutex:
                heapq.heappush(Ctrl.suspended, (t, sn, cond, cb))
            cond.acquire()
            cond.wait()
            cond.release()
        if cb is not None:
            return cb()
        return None
    @staticmethod
    def Wait(delay, cb=None):
        Ctrl.WaitUntil(Ctrl.GetSimTime() + delay, cb)
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
    def GetNetConfig():
        with Ctrl.mutex:
            ret = Ctrl.netConfig
        return ret
    @staticmethod
    def Freeze(toFreeze):
        '''
        Internal use only
        Freeze or unfreeze the simulation clock
        This is for those threads whose computational load is most spent on AirSim APIs
        '''
        tid = threading.get_native_id()
        Ctrl.freezeCond.acquire()
        if toFreeze:
            Ctrl.freezeSet.add(tid)
        elif tid in Ctrl.freezeSet:
            Ctrl.freezeSet.remove(tid)
            if len(Ctrl.freezeSet) == 0:
                Ctrl.freezeCond.notify()
        Ctrl.freezeCond.release()
    @staticmethod
    def Frozen():
        '''
        Context manager for time frozen
        to compensate extra time generated for simulation
        (simulation runs slower than real-time, for example take a high quality image in AirSim)
        '''
        return CtrlFrozen()
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
        
        # check for name validity
        for name in netConfig['uavsName']:
            if ' ' in name or 'GCS' in name:
                raise ValueError(f'UAV name: {name} is illegal, any whitespace or literally GCS is not allowd')
        
        self.zmqSendSocket.send_string(s)
        # rm timeout
        # self.zmqRecvSocket.setsockopt(zmq.RCVTIMEO, int(10*1000*netConfig["updateGranularity"]))
        self.netConfig = netConfig
        Ctrl.netConfig = netConfig
        Ctrl.SetEndTime(netConfig["endTime"])
        return netConfig
    
    def nextSimStepSize(self):
        '''
        return the next simulation step
        '''
        with self.mutex:
            # The suspended event occur earlier
            if len(Ctrl.suspended) > 0 and Ctrl.suspended[0][0] < Ctrl.simTime + self.netConfig['updateGranularity']:
                ret = Ctrl.suspended[0][0] - Ctrl.simTime
            else:
                ret = self.netConfig['updateGranularity']
        return ret
    def notifyWait(self):
        '''
        internal use only
        notfiy the waiting thread if delay is expired
        notify every waiting if simulation is not running
        '''
        with Ctrl.mutex:
            isRunning = Ctrl.isRunning
            tsim = Ctrl.simTime
            if isRunning:
                while len(Ctrl.suspended) > 0 and Ctrl.suspended[0][0] <= Ctrl.simTime + Ctrl.netConfig['updateGranularity']/2:
                    t, sn, cond, cb = Ctrl.suspended[0]
                    cond.acquire()
                    cond.notify()
                    cond.release()
                    heapq.heappop(Ctrl.suspended)
            else: # release all pending threads
                while len(Ctrl.suspended) > 0:
                    t, sn, cond, cb = heapq.heappop(Ctrl.suspended)
                    cond.acquire()
                    cond.notify()
                    cond.release()
    def advance(self):
        '''
        advace the simulation by a small step
        '''
        Ctrl.freezeCond.acquire()
        if len(Ctrl.freezeSet) != 0:
            # print(f'GCS, {len(Ctrl.freezeSet)}')
            Ctrl.freezeCond.wait()
        Ctrl.freezeCond.release()
        try:
            # ns3 has finished the previous simulation step
            if TIME_TEST:
                t0 = time.time()
            
            msg = self.zmqRecvSocket.recv()
            
            if TIME_TEST:
                t1 = time.time()
                self.nsSpent += (t1 - t0)
                print(f'<NS spent> {t1 - t0} sec')
            
            # this will block until resumed
            step = self.nextSimStepSize()
            self.client.simContinueForTime(step)
            with Ctrl.mutex:
                Ctrl.simTime += step
            self.zmqSendSocket.send_string(f'{step}')
            if TIME_TEST:
                t0 = time.time()
                self.AirSimSpent += (t0 - t1)
                print(f'<AirSim spent> {t0 - t1} sec')
            if VERBOSE:
                print(f'[Ctrl], Time = {Ctrl.simTime}')
            self.notifyWait()
        except zmq.ZMQError:
            print('ctrl msg not received')
    def run(self):
        '''
        control and advance the whole simulation
        '''
        if TIME_TEST:
            self.nsSpent = 0
            self.AirSimSpent = 0
        while Ctrl.ShouldContinue():
            self.advance()
        with Ctrl.mutex:
            Ctrl.isRunning = False
        self.zmqSendSocket.send_string(f'bye {Ctrl.GetEndTime()}')
        self.notifyWait()
        if TIME_TEST:
            print(f'<NS spent {self.nsSpent}>, <AirSim spent {self.AirSimSpent}>')

class CtrlFrozen():
    '''
    Context manager class for Ctrl.Frozen()
    '''
    def __init__(self):
        pass
    def __enter__(self):
        Ctrl.Freeze(True)
    def __exit__(self, exc_type, exc_value, tb):
        Ctrl.Freeze(False)