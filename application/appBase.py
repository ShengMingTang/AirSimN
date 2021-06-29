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
from appProtocolBase import MsgBase
from ctrl import *
from msg import *
from router import Flow, mainRouter

TARGET = 'stream' # 'selftest' | 'stream' | 'throughput'
DIST = 0
PERIOD = 0.01

class AppBase(metaclass=abc.ABCMeta):
    '''
    Any custom level application must inherit this
    implement Tx/Rx functions
    '''
    def __init__(self, name):
        super().__init__()
        self.name = name
    def Tx(self, obj, toName=None):
        '''
        @param obj: any object that supports __len__()
        To start a flow
        return len(obj)
        '''
        if isinstance(obj, (list, tuple)):
            for msg in obj:
                f = Flow(self.name, toName, msg)
                f.start()
            return [len(msg) for msg in obj]
        else:
            f = Flow(self.name, toName, obj)
            f.start()
            return len(obj)
        
    def Rx(self, block=False, timeout=None):
        '''
        @param block: bool, True than block until a msg has arrived (usually False)
        
        return None if msg is not fully received
        else
        return (src, msg)
        '''      
        return mainRouter.recv(self.name, block=block, timeout=timeout)

class UavAppBase(AppBase, threading.Thread):
    '''
    UavAppBase(name=name)
    '''
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
    def Tx(self, obj, toName=None):
        '''
        Syntax sugar for backward compatible
        toName will be 'GCS' by default if not specified
        '''
        toName = toName if toName is not None else 'GCS'
        super().Tx(obj, toName)
    def selfTest(self, **kwargs):
        '''
        Basic utility test including Tx, Rx, MsgRaw
        paired with GcsApp.selfTest()
        '''
        print(f'{self.name} is testing')
        Ctrl.WaitUntil(1.0, lambda: print(f'{self.name} at 1.0, got {Ctrl.GetSimTime()}'))
        Ctrl.Wait(0.95)
        with Ctrl.Frozen():
            print(f'{self.name} at frozen, got {Ctrl.GetSimTime()}')
        Ctrl.Wait(0.5234, lambda: print(f'{self.name} at 2.4734, got {Ctrl.GetSimTime()}'))
        msg = MsgRaw(b'I\'m %b' % (bytes(self.name, encoding='utf-8')))
        print(f'{self.name} trans msg at time {Ctrl.GetSimTime()}')
        self.Tx(msg)

        # compound send test
        msgs = [MsgRaw(b'I\'m %b-%d' % (bytes(self.name, encoding='utf-8'), i)) for i in range(5)]
        print(f'{self.name} trans multiple msg at time {Ctrl.GetSimTime()}')
        self.Tx(msgs)
        
        reply = None
        while Ctrl.ShouldContinue():
            reply = self.Rx()
            if reply is not None:
                print(f'{self.name} recv: {reply[1].data} at time {Ctrl.GetSimTime()}')
            Ctrl.Wait(0.01)
    def staticThroughputTest(self, dist, period, **kwargs):
        '''
        Run throughput test at application level
        dist argument must be specified
        paired with GcsApp.staticThroughputTest()
        '''
        delay = 1.0
        Ctrl.Wait(delay)
        client = airsim.MultirotorClient()
        client.confirmConnection()
        pose = client.simGetVehiclePose(vehicle_name=self.name)
        pose.position.x_val = dist
        
        total = 0
        msg = MsgRaw(bytes(50*1024))
        client.simSetVehiclePose(pose, True, vehicle_name=self.name)
        t0 = Ctrl.GetSimTime()
        while Ctrl.ShouldContinue():
            Ctrl.Wait(period)
            self.Tx(msg)
            total += len(msg.data)
        print(f'{dist} {self.name} trans {total}, throughput = {total*8/1000/1000/(Ctrl.GetEndTime()-t0)}')
    def streamingTest(self, **kwargs):
        '''
        Test Msg Level streaming back to GCS
        '''
        client = airsim.MultirotorClient()
        client.confirmConnection()
        client.enableApiControl(True, vehicle_name=self.name)
        client.armDisarm(True, vehicle_name=self.name)
        
        delay = 1.0
        Ctrl.Wait(delay)
        while Ctrl.ShouldContinue():
            Ctrl.Wait(0.1)
            with Ctrl.Frozen():
                rawImage = client.simGetImage("0", airsim.ImageType.Scene, vehicle_name=self.name)
                msg = MsgImg(rawImage, Ctrl.GetSimTime())
            self.Tx(msg)
    def run(self, *args, **kwargs):
        if TARGET == 'selftest':
            self.selfTest(*args, **kwargs)
        elif TARGET == 'throughput':
            self.staticThroughputTest(dist=DIST, period=PERIOD, *args, **kwargs)
        elif TARGET == 'stream':
            self.streamingTest(*args, **kwargs);
        print(f'{self.name} joined')
class GcsAppBase(AppBase, threading.Thread):
    '''
    GcsAppBase(name=name)
    '''
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
    def selfTest(self, *args, **kwargs):
        '''
        Basic utility test including Tx, Rx, MsgRaw
        paired with UavApp.selfTest()
        '''
        Ctrl.Wait(3.0)
        print(f'{self.name} is testing')
        msg = MsgRaw(b'I\'m GCS')
        print(f'{self.name} trans msg to A at time {Ctrl.GetSimTime()}')
        self.Tx(msg, 'A')
        print(f'{self.name} trans msg to B at time {Ctrl.GetSimTime()}')
        self.Tx(msg, 'B')

        # compound send test
        msgs = [MsgRaw(b'I\'m %b-%d' % (bytes(self.name, encoding='utf-8'), i)) for i in range(5)]
        print(f'{self.name} trans multiple msg to A at time {Ctrl.GetSimTime()}')
        self.Tx(msgs, 'A')
        print(f'{self.name} trans multiple msg to A at time {Ctrl.GetSimTime()}')
        self.Tx(msgs, 'B')
        
        while Ctrl.ShouldContinue():
            reply = self.Rx()
            if reply is not None:
                print(f'{self.name} recv: {reply[1].data}  at time {Ctrl.GetSimTime()}')
            Ctrl.Wait(0.01)
    def staticThroughputTest(self, *args, **kwargs):
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
        delay = 1.0
        Ctrl.Wait(delay)
        fig = None
        while Ctrl.ShouldContinue():
            reply = self.Rx()
            if reply is not None:
                name, reply = reply
                png = cv2.imdecode(airsim.string_to_uint8_array(reply.png), cv2.IMREAD_UNCHANGED)
                png = cv2.cvtColor(png, cv2.COLOR_BGRA2BGR)
                if fig is None:
                    fig = plt.imshow(png)
                    Ctrl.SetEndTime(Ctrl.GetSimTime() + 2.0)
                else:
                    fig.set_data(png)
            else:
                plt.pause(0.1)
            plt.draw()
        plt.clf()
    def run(self, *args, **kwargs):
        if TARGET == 'selftest':
            self.selfTest(*args, **kwargs)
        elif TARGET == 'throughput':
            self.staticThroughputTest(*args, **kwargs)
        elif TARGET == 'stream':
            self.streamingTest(*args, **kwargs);
        print(f'{self.name} joined')