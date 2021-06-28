
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
    def __enter__(self):
        self.lock.acquire()
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
        self.senderSrc2Dst = {} # flow record on sender side
        self.recverSrc2Dst = {} # flow record on recver side
        
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
                self.endPoints[f.src].zmqSendSocket.send_string(f'{f.id} {FLOWOP_SEND} {f.size} {f.dst}', 0)
                self.senderSrc2Dst[f.src][f.dst].append(f)
                self.recverSrc2Dst[f.src][f.dst].append(f)
        return f
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
    def recv(self, dst, block=False):
        '''
        Allow an application to retrieve object
        An object is visible if that corresponding flow is fully received
        '''
        try:
            f = self.endPoints[dst].queue.get(block=block)
            return (f.src, f.msg)
        except queue.Empty:
            return None
    def compile(self):
        '''
        To build a connected graph and do house-keeping
        '''
        with self.mutex:
            for src in self.endPoints:
                d = {}
                for dst in self.endPoints:
                    d[dst] = deque()
                self.senderSrc2Dst[src] = d
                self.recverSrc2Dst[src] = d
    def run(self):
        # Keep listening to reponse from NS3 then update those flows
        while Ctrl.ShouldContinue():
            try:
                msg = self.sub.recv_string()
                src, dst, op, *args = msg.split()
                if op == FLOWOP_SEND:
                    # <src> <dst> "SEND" <size>
                    with self.mutex:
                        f = self.senderSrc2Dst[src][dst].popleft()
                        size = int(args[0])
                        print(f'{src}->{dst} send {size}')
                        with f:
                            f.bytesSent += size
                            if f.bytesSent == f.size:
                                pass
                            elif f.bytesSent < f.size:
                                self.senderSrc2Dst[src][dst].appendleft(f)
                            else:
                                raise RuntimeError(f'{f} calculation Error on sender side')
                elif op == FLOWOP_RECV:
                    with self.mutex:
                        size = int(args[0])
                        print(f'{src}->{dst} recv {size}')
                        f = self.recverSrc2Dst[src][dst].popleft()
                        with f:
                            f.bytesRecv += size
                            if f.bytesRecv == f.size:
                                self.endPoints[f.dst].queue.put_nowait(f)
                            elif f.bytesRecv < f.size:
                                self.recverSrc2Dst[src][dst].appendleft()
                            else:
                                raise RuntimeError(f'{f} calculation Error on recver side')
                else:
                    raise RuntimeError('In Router, OP {op} not handled')
            except zmq.ZMQError:
                pass

# instantiate a common router for the whole simulation
context = zmq.Context(NUM_IO_THREADS)
mainRouter = Router(context)