import sys, inspect
import numpy as np
from appProtocolBase import MsgBase
import pickle

'''
Custom message
Note:
    MsgBase-like object is not needed for AppBase.Tx(...) anymore
    Objects that has __len__() are allowed to be transmitted
    MsgBase-like object is not recommended since serialization may consume extra resources
'''  
class MsgRaw(MsgBase):
    '''
    The simplest MsgBase subclass
    directly transform data to bytes if possible
    '''
    def __init__(self, data=bytes(0), **kwargs):
        self.data = data
        
    @classmethod
    def GetTypeId(self):
        return 0
    def serialize(self):
        return bytes(self.data)
    @classmethod
    def Deserialize(cls, data):
        return MsgRaw(data)
    def __str__(self):
        return str(self.data)
class MsgImg(MsgBase):
    def __init__(self, png=np.zeros((0,)), timestamp=0.0, **kwargs):
        self.png = png
        self.timestamp = timestamp
    @classmethod
    def GetTypeId(self):
        return 2
    def serialize(self):
        return pickle.dumps(self)
    @classmethod
    def Deserialize(cls, data):
        return pickle.loads(data)
    def __str__(self):
        return f'ts:{self.timestamp}, img size:{np.size(self.png)}'

# summary
MsgProtocol = {}
for name, obj in inspect.getmembers(sys.modules[__name__]):
    if inspect.isclass(obj) and issubclass(obj, MsgBase):
        if obj != MsgBase:
            if obj().GetTypeId() in MsgProtocol:
                raise ValueError(f'{obj().GetTypeId()} is already registered')
            else:
                MsgProtocol[obj().GetTypeId()] = obj
 