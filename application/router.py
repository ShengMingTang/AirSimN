
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
    Direct attribute access is not Thread Safe
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
class FlowOp(Enum):
    '''
    Protocol: Flow.id, Flowop, args...
    '''
    SEND = 'SEND'
    RECV = 'RECV'
    STOP = 'STOP'
class EndPoint():
    def __init__(self, zmqSendSocket, *args, **kwargs):
        self.zmqSendSocket = zmqSendSocket
        self.queue = queue.Queue()
class Router(threading.Thread):
    def __init__(self, context, *args, **kwargs):
        super().__init__()
        # [name] -> endPoint
        self.endPoints = {}
        self.flowIDCount = 0
        self.context = context
        self.sub = context.socket(zmq.SUB)
        self.sub.bind(f'tcp://*:{NS2ROUTER_PORT}')
        self.sub.setsockopt(zmq.RCVTIMEO, IOTIMEO)
        
        # [src][dst] -> deque
        # left (oldest) ... right (latest)
        self.senderSrc2Dst = {}
        self.recverSrc2Dst = {}
        
        self.mutex = threading.Lock()
    def startFlow(self, f):
        '''
        <flowid> "SEND" <size> <dst>
        
        NS3 should start its flow and keep transmitting to zmqRecvSocket
        <src(this)> <dst> "SEND" <size>
        '''
        with f:
            if f.id >= 0:
                raise RuntimeError(f'flowid {f.id} is started')
            with self.mutex:
                f.id = self.flowIDCount
                self.flowIDCount += 1
                print(f'Router sends "{f.id} {FLOWOP_SEND} {f.size} {f.dst}"')
                self.endPoints[f.src].zmqSendSocket.send_string(f'{f.id} {FLOWOP_SEND} {f.size} {f.dst}', 0)
                self.senderSrc2Dst[f.src][f.dst].append(f)
                self.recverSrc2Dst[f.src][f.dst].append(f)
        return f
    def register(self, name, zmqSendPort, *args, **kwargs):
        zmqSendSocket = self.context.socket(zmq.PUSH)
        zmqSendSocket.bind(f'tcp://*:{zmqSendPort}')
        zmqSendSocket.setsockopt(zmq.RCVTIMEO, IOTIMEO)
        with self.mutex:
            self.endPoints[name] = EndPoint(zmqSendSocket)
            return self.endPoints[name]
    def recv(self, dst, block=False):
        '''
        Let application retrieve object that is completely transmitted
        '''
        try:
            f = self.endPoints[dst].queue.get(block=block)
            return (f.src, f.msg)
        except queue.Empty:
            return None
    def compile(self):
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
                msg = self.sub.recv_string(zmq.NOBLOCK)
                src, dst, op, *args = msg.split()
                if op == FLOWOP_SEND:
                    # <src> <dst> "SEND" <size>
                    with self.mutex:
                        f = self.senderSrc2Dst[src][dst].popleft()
                        size = int(args[0])
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
                    raise RuntimeError('OP {op} not handled')
            except zmq.ZMQError:
                pass
                

context = zmq.Context(NUM_IO_THREADS)
mainRouter = Router(context)