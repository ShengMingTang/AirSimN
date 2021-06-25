import abc
from typing import Type
import zmq
import sys
import re
import threading
import queue
import time
import cv2

import setup_path
import airsim
import numpy as np
import matplotlib.pyplot as plt
from appProtocolBase import AppSerializer, MsgBase
from ctrl import *
from msg import *


IOTIMEO = 1000 # I/O timeout for AppReceiver and AppSender

class AppReceiver(threading.Thread):
    '''
    This thread runs as an attribute of AppBase to receive bytes in the background
    isAddressPrefixed: True then all byte I/O will be prefixed with toName/fromName
    zmqLevel transmission syntax: (name)?[ ](bytes)
    zmqRecvPort, context
    '''
    def __init__(self, isAddressPrefixed, zmqRecvPort, context, msgProtocol, **kwargs):
        super().__init__()
        self.mutex = threading.Lock()
        self.isAddressPrefixed = isAddressPrefixed
        self.desrler = AppSerializer()
        self.deSrlers = {}
        self.msgs = queue.Queue()
        self.stopFlag = False
        self.msgProtocol = msgProtocol
        
        self.zmqRecvSocket = context.socket(zmq.PULL)
        self.zmqRecvSocket.connect(f'tcp://localhost:{zmqRecvPort}')
        self.zmqRecvSocket.setsockopt(zmq.RCVTIMEO, IOTIMEO)
    def recvMsg(self, block):
        '''
        return FIFO scheme complete MsgBase object in self.msgs if addressNotPrefixed
        return (addr, MsgBase) if address is prefixed      
        return None if no complete MsgBase object is received
        '''
        try:
            if self.isAddressPrefixed:
                addr, data = self.msgs.get(block=block)
                tid, bt = data
                return (addr, self.msgProtocol[tid].Deserialize(bt))
            else:
                data = self.msgs.get(block=block)
                tid, bt = data
                return self.msgProtocol[tid].Deserialize(bt)
        except queue.Empty:
            return None
    def setStopFlag(self):
        '''
        must be called if receiving process is about to end
        this thread will not join successfully if stopFlag is not set
        '''
        with self.mutex:
            self.stopFlag = True
    def run(self, **kwargs):
        '''
        run until stopFlag is set
        keep receiving raw bytes and push them into self.msgs in FIFO scheme
        use self.recvMsg() to retrieve MsgBase obj
        '''
        while self.stopFlag is False:
            try:
                fromName = None
                msg = self.zmqRecvSocket.recv()
                if self.isAddressPrefixed:
                    s, e = re.search(b" ", msg).span()
                    fromName = msg[:s].decode('ascii')
                    msg = msg[s+1:]
                    if fromName not in self.deSrlers:
                        self.deSrlers[fromName] = AppSerializer()
                    data = self.deSrlers[fromName].deserialize(msg)
                    for datum in data:
                        self.msgs.put_nowait((fromName, datum))
                else:
                    data = self.desrler.deserialize(msg)
                    for datum in data:
                        self.msgs.put_nowait(datum)
            except:
                pass
class AppSender(threading.Thread):
    def __init__(self, isAddressPrefixed, zmqSendPort, context, **kwargs):
        super().__init__()
        self.mutex = threading.Lock()
        self.isAddressPrefixed = isAddressPrefixed
        self.srler = AppSerializer()
        self.msgs = queue.Queue()
        self.packetSize = Ctrl.GetNetConfig()['TcpSndBufSize'] // 5
        self.lastPacket = None
        self.packets = queue.Queue()
        self.stopFlag = False
        self.count = 0
                
        self.zmqSendSocket = context.socket(zmq.REQ)
        self.zmqSendSocket.bind(f'tcp://*:{zmqSendPort}')
        self.zmqSendSocket.setsockopt(zmq.RCVTIMEO, IOTIMEO)
    def sendMsg(self, msg, toName):
        if self.isAddressPrefixed is False and toName is not None:
            raise ValueError('isAddressPrefixed False but toName is specified')
        elif self.isAddressPrefixed is True and toName is None:
            raise ValueError('isAddressPrefixed True but toName is NOT specified')
        
        with self.mutex:
            stopFlag = self.stopFlag
            count = self.count
            self.count += 1
        if stopFlag is False:
            try:
                self.msgs.put_nowait((count, msg, toName))
                return True
            except queue.Full:
                return False
        return False
    def flushMsgs(self):
        with self.mutex:
            while self.msgs.empty() is False:
                self.msgs.get_nowait()
    def setStopFlag(self):
        '''
        must be called if receiving process is about to end
        this thread will not join successfully if stopFlag is not set
        '''
        with self.mutex:
            self.stopFlag = True
    def run(self, **kwargs):
        while self.stopFlag is False:
            if self.lastPacket is None: # last one is finished
                if self.packets.empty() is False: # we have next one to transmit
                    self.lastPacket = self.packets.get_nowait()
                else: # decompose next msg if any
                    try:
                        c, msg, toName = self.msgs.get(True, IOTIMEO/1000)
                        bt = self.srler.serialize(msg)
                        # decompose to packets
                        for i in range(0, len(bt), self.packetSize):
                            self.packets.put_nowait((toName, bt[i*self.packetSize:(i+1)*self.packetSize]))
                    except queue.Empty:
                        pass
            else: # proceed to next one
                toName, payload = self.lastPacket
                if toName is not None:
                    payload = b'%b %b' % (bytes(toName, encoding='utf-8'), payload)
                    # print(toName, payload)
                try:
                    self.zmqSendSocket.send(payload, flags=zmq.NOBLOCK)    
                    res = self.zmqSendSocket.recv()
                    res = int.from_bytes(res, sys.byteorder, signed=True)
                    if res >= 0: # success, jump to next packet
                        self.lastPacket = None
                except zmq.ZMQError:
                    pass

class AppBase(metaclass=abc.ABCMeta):
    '''
    Any custom level application must inherit this
    implement Tx/Rx functions
    '''
    def __init__(self, zmqSendPort, context, **kwargs):
        super().__init__()
        self.zmqSendSocket = context.socket(zmq.REQ)
        self.zmqSendSocket.bind(f'tcp://*:{zmqSendPort}')
        self.zmqSendSocket.setsockopt(zmq.RCVTIMEO, 1000)
        self.srler = AppSerializer()
        self.recvThread = AppReceiver(context=context, msgProtocol=MsgProtocol, **kwargs)
        self.transmitSize = Ctrl.GetNetConfig()['TcpSndBufSize']
    def Tx(self, obj, toName=None, block=False):
        '''
        raise TypeError if toName is specified in UAV mode (isAddressPrefixed set to False) in both cases
        If obj is NOT iterable:
            return int as the same in ns socket->Send()
        If obj is iterable:
            this fn will transmit as much as it can until total size reaches self.transmitSize
            return [r_0, r_1 , r_2, ...]
            r_i > 0 means that msg in this index is transmitted successfully
            r_i < 0 means it is not transmitted or network congested (cannot fit into buffer)
        '''
        flags = zmq.NOBLOCK if block is False else 0
        try:
            sz = 0
            msgs = iter(obj)
            payload = bytes(0)
            ret = [-1 for msg in iter(obj)]
            for i, msg in enumerate(msgs):
                if isinstance(msg, MsgBase) is False:
                    raise TypeError('obj should be an instance of MsgBase')
                # serialize
                thisPayload = self.srler.serialize(msg)
                if toName is not None:
                    if self.recvThread.isAddressPrefixed is False:
                        raise TypeError('isAddressPrefixed set to False but desition is specified')
                    thisPayload = b'%b %b' % (bytes(toName, encoding='utf-8'), thisPayload)
                sz += len(thisPayload)
                if sz < self.transmitSize:
                    payload += thisPayload
                    ret[i] = len(thisPayload)
                else:
                    break
            try:
                self.zmqSendSocket.send(payload, flags=flags)
                res = self.zmqSendSocket.recv()
                res = int.from_bytes(res, sys.byteorder, signed=True)
                return ret
            except zmq.ZMQError: # all error
                return [-1 for i in iter(obj)]
        except:
            if isinstance(obj, MsgBase) is False:
                raise TypeError('obj should be an instance of MsgBase')
            # serialize
            payload = self.srler.serialize(obj)
            if toName is not None:
                if self.recvThread.isAddressPrefixed is False:
                    raise TypeError('isAddressPrefixed set to False but desition is specified')
                payload = b'%b %b' % (bytes(toName, encoding='utf-8'), payload)
            try:
                self.zmqSendSocket.send(payload, flags=flags)
                res = self.zmqSendSocket.recv()
                res = int.from_bytes(res, sys.byteorder, signed=True)
                return res
            except zmq.ZMQError:
                return -1

    def Rx(self, block=False):
        '''
        return None if a complete MsgBase is not received
        else
        return MsgBase if isAddressPrefixed is False
        return (fromName, MsgBase) otherwise
        '''      
        return self.recvThread.recvMsg(block)
    def beforeRun(self):
        self.recvThread.start()
    def afterRun(self):
        self.recvThread.setStopFlag()
        self.recvThread.join()
    @abc.abstractmethod
    def run(self, **kwargs):
        '''
        # Template
        self.beforeRun()
        
        # custom code
        self.customFn()
        # custom code
        
        self.afterRun()
        
        self.customFn():
            # Add small amount of delay(1.0s) before transmitting anything in your target function
            # This is for ns to have time to set up everything
            client.enableApiControl(True, vehicle_name=self.name)
            client.armDisarm(True, vehicle_name=self.name)
        '''
        return NotImplemented

class UavAppBase(AppBase, threading.Thread):
    '''
    UavAppBase(name=name, iden=i, context=context)
    '''
    def __init__(self, name, iden, **kwargs):
        kwargs['isAddressPrefixed'] = False
        kwargs['zmqSendPort'] = AIRSIM2NS_PORT_START+iden
        kwargs['zmqRecvPort'] = NS2AIRSIM_PORT_START+iden
        super().__init__(**kwargs)
        self.name = name
                       
    def selfTest(self, **kwargs):
        '''
        Basic utility test including Tx, Rx, MsgRaw
        paired with GcsApp.selfTest()
        '''
        delay = 1.0
        Ctrl.Wait(delay)
        print(f'{self.name} is testing')
        msg = MsgRaw(b'I\'m %b' % (bytes(self.name, encoding='utf-8')))
        while self.Tx(msg) < 0:
            print(f'{self.name} trans fail')
        print(f'{self.name} trans msg')

        # compound send test
        msgs = [msg for i in range(5)]
        res = [-1 for i in range(len(msgs))]
        print(f'{self.name} is sending multiple msg to GCS')
        while sum(res) < 0:
            res = self.Tx(msgs)
        print(f'{self.name} sents multiple msg with res={res}')

        reply = None
        while Ctrl.ShouldContinue():
            time.sleep(0.1)
            reply = self.Rx()
            if reply is not None:
                print(f'{self.name} recv: {reply}')
            else:
                # print(f'{self.name} recv: {reply}')
                pass
    def staticThroughputTest(self, dist=0, period=0.01, **kwargs):
        '''
        Run throughput test at application level
        dist argument must be specified
        paired with GcsApp.staticThroughputTest()
        '''
        delay = 0.2
        Ctrl.Wait(delay)
        total = 0
        client = airsim.MultirotorClient()
        client.confirmConnection()
        pose = client.simGetVehiclePose(vehicle_name=self.name)
        pose.position.x_val = dist
        lastTx = Ctrl.GetSimTime()
        msg = MsgRaw(bytes(50*1024))
        client.simSetVehiclePose(pose, True, vehicle_name=self.name)
        t0 = Ctrl.GetSimTime()
        while Ctrl.ShouldContinue():
            Ctrl.Wait(period)
            res = self.Tx(msg)
            if res > 0:
                total += len(msg.data)
        print(f'{dist} {self.name} trans {total}, throughput = {total*8/1000/1000/(Ctrl.GetEndTime()-delay)}')
    def streamingTest(self, **kwargs):
        '''
        Test Msg Level streaming back to GCS
        '''
        client = airsim.MultirotorClient()
        client.confirmConnection()
        client.enableApiControl(True, vehicle_name=self.name)
        client.armDisarm(True, vehicle_name=self.name)
        
        delay = 0.2
        Ctrl.Wait(delay)
        # client.takeoffAsync(vehicle_name=self.name).join()
        # client.moveByVelocityBodyFrameAsync(5, 0, 0, 20, vehicle_name=self.name)
        while Ctrl.ShouldContinue():
            Ctrl.Wait(0.1)
            rawImage = client.simGetImage("0", airsim.ImageType.Scene, vehicle_name=self.name)
            png = cv2.imdecode(airsim.string_to_uint8_array(rawImage), cv2.IMREAD_UNCHANGED)
            msg = MsgImg(png, Ctrl.GetSimTime())
            res = self.Tx(msg)
            if res < 0:
                print(f'{self.name} streaming res = {res}')
    def run(self, **kwargs):
        self.beforeRun()
        self.selfTest()
        # self.streamingTest();
        self.afterRun()
        print(f'{self.name} joined')
class GcsAppBase(AppBase, threading.Thread):
    '''
    GcsAppBase(context=context)
    '''
    def __init__(self, runner=None, args=None, **kwargs):
        kwargs['isAddressPrefixed'] = True
        kwargs['zmqSendPort'] = AIRSIM2NS_GCS_PORT
        kwargs['zmqRecvPort'] = NS2AIRSIM_GCS_PORT
        super().__init__(**kwargs)
        self.name = 'GCS'
    def selfTest(self, **kwargs):
        '''
        Basic utility test including Tx, Rx, MsgRaw
        paired with UavApp.selfTest()
        '''
        delay = 1.0
        Ctrl.Wait(delay)
        print(f'{self.name} is testing')
        msg = MsgRaw(b'I\'m GCS')
        while self.Tx(msg, 'A') is False:
            time.sleep(0.1)
        print(f'GCS trans to A')
        while self.Tx(msg, 'B') is False:
            time.sleep(0.1)
        print(f'GCS trans to B')

        # compound send test
        msgs = [msg for i in range(5)]
        res = [-1 for i in range(len(msgs))]
        print('GCS is sending multiple msg to A')
        while sum(res) < 0:
            res = self.Tx(msgs, toName='A')
        print(f'{self.name} sents multiple msg to A with res={res}')

        res = [-1 for i in range(len(msgs))]
        print('GCS is sending multiple msg to B')
        while sum(res) < 0:
            res = self.Tx(msgs, toName='B')
        print(f'{self.name} sents multiple msg to B with res={res}')

        while Ctrl.ShouldContinue():
            reply = self.Rx()
            if reply is None:
                time.sleep(0.1)
            else:
                name, reply = reply
                print(f'{self.name} recv: {reply} from {name}')
    def staticThroughputTest(self, **kwargs):
        '''
        Run throughput test at application level
        paired with UavApp.staticThroughputTest()
        '''
        total = 0
        delay = 0.1
        Ctrl.Wait(delay)
        t0 = Ctrl.GetSimTime()
        while Ctrl.ShouldContinue():
            msg = self.Rx()
            if msg is not None:
                addr, msg = msg
                total += len(msg.data)
        print(f'GCS recv {total}, throughput = {total*8/1000/1000/(Ctrl.GetEndTime()-(t0))}')
    def streamingTest(self, **kwargs):
        '''
        Test Msg Level streaming back to GCS
        '''
        delay = 0.1
        Ctrl.Wait(delay)
        fig = None
        while Ctrl.ShouldContinue():
            reply = self.Rx()
            if reply is not None:
                name, reply = reply
                # print(f'GCS recv {reply}')
                
                if fig is None:
                    fig = plt.imshow(reply.png)
                else:
                    fig.set_data(reply.png)
            else:
                pass
            plt.pause(0.1)
            plt.draw()
        plt.clf()
    def run(self, **kwargs):
        self.beforeRun()
        self.selfTest()
        # self.streamingTest();
        self.afterRun()
        print(f'{self.name} joined')
