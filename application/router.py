
import sys
import threading
from enum import Enum
import queue
from collections import deque
# custom imports
from ctrl import *

FLOWOP_SEND="SEND"
FLOWOP_RECV="RECV"
FLOWOP_STOP="STOP"

IOTIMEO = 1000
NUM_IO_THREADS = 5
VERBOSE=False

class Flow():
    '''
    Note:
        There should be no direct, related call of this class
        (considered as static class)
        A flow cannot be stopped once it is started
    Usage:
        f = Flow(src, dst, msg)
        f.start() # trigger by AppBase.Tx(...)
        # direct attribute access is not thread safe
        with f:
            # access attribute here
            pass
    '''
    def __init__(self, src, dst, msg):
        self.id = -1
        self.src = src
        self.dst = dst
        self.msg = msg
        self.bytesSent = 0
        self.bytesRecv = 0
        self.size = len(msg)
        self.lock = threading.Lock()
    def start(self):
        return mainRouter.startFlow(self)
    # def stop(self):
    #     return mainRouter.stopFlow(self)
    def isStarted(self):
        with self:
            return self.bytesSent != 0
    def isStopped(self):
        with self:
            return self.size == -1
    def isDone(self):
        with self:
            return self.bytesSent == self.bytesRecv
    def __str__(self):
        '''
        Not thread safe print
        Must be enclosed in
        with self() :
            # code
        '''
        return f'Flow: {self.id} size:{self.size}, sent:{self.bytesSent}, recv:{self.bytesRecv}'
    def __enter__(self):
        self.lock.acquire()
        return self
    def __exit__(self, exc_type, exc_value, tb):
        self.lock.release()
class EndPoint():
    '''
    Store zmq socket to talk to NS3 application
    * to trigger request ( usually after Flow.start() )
    * to store receiver side queue for py app
    '''
    def __init__(self, zmqSendSocket, *args, **kwargs):
        self.zmqSendSocket = zmqSendSocket
        self.queue = queue.Queue()
class Router(threading.Thread):
    '''
    Control of application data Flow
    This class is optimized for data passing to avoid redundant data copying.
    Usage:
    router = Router(zmq.context(int))
    # to tell router which port it should use to deliver request
    router.register(name, port)
    # after register all (name, port) pairs
    router.compile() # to build an connected channel for sender side and recver side
    '''
    def __init__(self, context, *args, **kwargs):
        super().__init__()
        self.flowIDCount = 0
        self.context = context
        self.sub = context.socket(zmq.PULL)
        self.sub.bind(f'tcp://*:{NS2ROUTER_PORT}')
        self.sub.setsockopt(zmq.RCVTIMEO, IOTIMEO)
        
        # [name] -> endPoint
        self.endPoints = {}
        
        # [src][dst] -> deque
        # left (oldest) ... right (latest)
        self.recverSrc2Dst = {} # flow record on recver side
        self.flows = {} # fid->flow
        self.mutex = threading.Lock()
    def startFlow(self, f):
        '''
        request deliver to NS
        <flowid> "SEND" <size> <dst>
        
        NS3 should start its flow and keep transmitting to zmqRecvSocket
        <src(this)> <dst> "SEND" <size>
        
        return f (itself)
        '''
        with f:
            if f.id >= 0:
                raise RuntimeError(f'flowid {f.id} is already started')
            with self.mutex:
                f.id = self.flowIDCount
                self.flowIDCount += 1
                self.recverSrc2Dst[f.src][f.dst].append(f)
                self.flows[f.id] = f
                self.endPoints[f.src].zmqSendSocket.send_string(f'{f.id} {FLOWOP_SEND} {f.size} {f.dst}', 0)
                if VERBOSE:
                    print(f'Router req: {f.id} {f.src} {FLOWOP_SEND} {f.size} {f.dst}')
        return f
    # def stopFlow(self, f):
    #     '''
    #     Just send stop request,
    #     The record is removed after receiving response from NS
    #     stop req
    #     <flowid> "STOP" 
        
    #     NS3 should respond
    #     <src> <dst> "STOP" <succ=0/1> <fid> <left>
        
    #     return f (itself)
    #     '''
    #     with f:
    #         if f.id < 0:
    #             raise RuntimeError(f'flowid {f.id} not started but set stopped')
    #         # flow itself is not modified, to keep the previous transmission message correct
    #         with self.mutex:
    #             self.endPoints[f.src].zmqSendSocket.send_string(f'{f.id} {FLOWOP_STOP} ', 0)
    #             if VERBOSE:
    #                 print(f'Router req: {f.id} {FLOWOP_STOP} ')
                
    def register(self, name, zmqSendPort, *args, **kwargs):
        '''
        To register an entry for an application (in py and NS)
        '''
        zmqSendSocket = self.context.socket(zmq.PUSH)
        zmqSendSocket.bind(f'tcp://*:{zmqSendPort}')
        zmqSendSocket.setsockopt(zmq.RCVTIMEO, IOTIMEO)
        with self.mutex:
            self.endPoints[name] = EndPoint(zmqSendSocket)
            return self.endPoints[name]
    def recv(self, dst, block, timeout):
        '''
        To Allow an application to retrieve object
        An object is visible if that corresponding flow is fully received
        '''
        try:
            with self.mutex:
                f = self.endPoints[dst].queue.get(block=block, timeout=timeout)
                return (f.src, f.msg)
        except queue.Empty:
            return None
    def compile(self):
        '''
        To build a connected graph and do house-keeping
        '''
        with self.mutex:
            for src in self.endPoints:
                dd = {}
                for dst in self.endPoints:
                    dd[dst] = deque()
                self.recverSrc2Dst[src] = dd
    def run(self):
        # Keep listening to reponse from NS3 then update those flows
        while Ctrl.ShouldContinue():
            try:
                msg = self.sub.recv_string()
                src, dst, op, *args = msg.split()
                if op == FLOWOP_SEND:
                    # <src> <dst> "SEND" <size> <fid>
                    size = int(args[0])
                    fid = int(args[1])
                    if VERBOSE:
                        print(f'fid: {fid}, {src}-S>{dst} send {size}')
                    with self.mutex:
                        if fid in self.flows:
                            with self.flows[fid] as f:
                                f.bytesSent += size
                # sendCallback fired from NS3 will be aggregated
                # <size> may be the sum of several packets
                elif op == FLOWOP_RECV:
                    # <src> <dst(this)> "RECV" <size>
                    with self.mutex:
                        size = int(args[0])
                        if VERBOSE:
                            print(f'{src}-R>{dst} recv {size}')
                        while size > 0:
                            f = self.recverSrc2Dst[src][dst].popleft()
                            with f:
                                if f.id in self.flows: # hasn't been removed yet
                                    put = min(size, f.size - f.bytesRecv)
                                    f.bytesRecv += put
                                    size -= put
                                    if f.bytesRecv == f.size:
                                        self.endPoints[f.dst].queue.put_nowait(f)
                                    elif f.bytesRecv < f.size:
                                        self.recverSrc2Dst[src][dst].appendleft(f)
                                    else:
                                        raise RuntimeError(f'{f} calculation Error on recver side')
                                else: # flow f is canceled
                                    pass
                # elif op == FLOWOP_STOP:
                #     # <src> <dst> "STOP" <succ=0/1> <fid> <left>
                #     succ = int(args[0])
                #     fid = int(args[1])
                #     left = int(args[2])
                #     if VERBOSE:
                #         print(f'{src}-x-{dst} stopped, succ {succ}, fid {fid}, left {left}')
                #     if succ == 1:
                #         self.flows.pop(fid)
                else:
                    raise RuntimeError(f'In Router, OP "{op}" not handled')
            except zmq.ZMQError:
                pass

# instantiate a common router for the whole simulation
context = zmq.Context(NUM_IO_THREADS)
mainRouter = Router(context)