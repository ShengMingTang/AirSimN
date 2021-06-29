import abc
import sys
from enum import Enum
import hashlib

MOUDLE_DEBUG = False

class MsgBase(metaclass=abc.ABCMeta):
    '''
    # // Any application Msg should inherit this
    '''
    @abc.abstractmethod
    def GetTypeId(self):
        '''
        return an int ranging in (0,255]
        User is responsible for collision-free choice of TypeId
        '''
        return NotImplemented
    @abc.abstractmethod
    def serialize(self):
        '''
        return bytes representation of the obj itself
        '''
        return NotImplemented
    @classmethod
    @abc.abstractmethod
    def Deserialize(cls, data):
        '''
        classmethod (Of course, the object itself is not known before reconstructed)
        Take raw bytes as input and return the reconstructed object
        '''
        return NotImplemented
    @abc.abstractmethod
    def __str__(self):
        return NotImplemented
    
    def __len__(self):
        return len(self.serialize())