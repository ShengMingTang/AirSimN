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

IOTIMEO = 3000 # in ms to let AppReceiver have a chance to break
TARGET = 'selftest' # 'selftest' | 'stream

class AppBase(metaclass=abc.ABCMeta):
    '''
    Any custom level application must inherit this
    implement Tx/Rx functions
    '''
    def __init__(self, name):
        super().__init__()
        self.name = name
    def Tx(self, obj, toName=None, block=False):
        '''
        To start flow(s)
        '''
        f = Flow(self.name, toName, obj)
        f.start()
        return len(obj)
        
    def Rx(self, block=False):
        '''
        return None if a complete msg is not received
        else
        return (src, msg)
        '''      
        return mainRouter.recv(self.name, block)

class UavAppBase(AppBase, threading.Thread):
    '''
    UavAppBase(name=name, iden=i, context=context)
    '''
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
    def Tx(self, obj):
        super().Tx(obj, 'GCS')   
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
        self.Tx(msg)
        print(f'{self.name} trans msg')

        reply = None
        while Ctrl.ShouldContinue():
            reply = self.Rx()
            if reply is not None:
                print(f'{self.name} recv: {reply}')
            else:
                Ctrl.Wait(0.5)
    def staticThroughputTest(self, dist=0, period=0.01, **kwargs):
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
            res = self.Tx(msg)
            if res > 0:
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
    def run(self, *args, **kwargs):
        if TARGET == 'selftest':
            self.selfTest(*args, **kwargs)
        elif TARGET == 'stream':
            self.streamingTest(*args, **kwargs);
        print(f'{self.name} joined')
class GcsAppBase(AppBase, threading.Thread):
    '''
    GcsAppBase(context=context)
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
        self.Tx(msg, 'A')
        print(f'GCS trans to A')
        self.Tx(msg, 'B')
        print(f'GCS trans to B')

        while Ctrl.ShouldContinue():
            reply = self.Rx()
            if reply is not None:
                print(f'{self.name} recv: {reply}')
            else:
                Ctrl.Wait(0.5)
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
        delay = 0.1
        Ctrl.Wait(delay)
        fig = None
        while Ctrl.ShouldContinue():
            reply = self.Rx()
            if reply is not None:
                name, reply = reply
                
                if fig is None:
                    fig = plt.imshow(reply.png)
                else:
                    fig.set_data(reply.png)
            else:
                pass
            plt.pause(0.1)
            plt.draw()
        plt.clf()
    def run(self, *args, **kwargs):
        if TARGET == 'selftest':
            self.selfTest(*args, **kwargs)
        elif TARGET == 'stream':
            self.streamingTest(*args, **kwargs);
        print(f'{self.name} joined')