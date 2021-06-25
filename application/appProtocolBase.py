import abc
import sys
from enum import Enum
import hashlib

MOUDLE_DEBUG = False

class MsgBase(metaclass=abc.ABCMeta):
    '''
    Any application Msg should inherit this
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

class AppSerializerState(Enum):
    '''
    State an AppSerializer may encounter
    '''
    TID = 0 # wait for typeId
    LEN = 1 # wait for len field
    DATA = 2 # wait for data
    CHECKSUM = 3 # wait for checksum
class AppSerializer():
    '''
    Responsible for serialize/deserialize obj
    This implements a simple LL(1) parser
    '''
    TID_SIZE = 1
    LEN_SIZE = 4 # 4.29 GB
    DIGEST_SIZE = 1
    def __init__(self):
        self.buffer = bytes(0)
        # parsing self.buffer states
        self.state = AppSerializerState.TID
        self.stateTid = None
        self.stateLen = None
        self.stateData = bytes(0)
    def serialize(self, obj):
        '''
        serialize obj to specific format of bytes
        (typeId, len, bytes)
        raise TypeError obj is not an instance of MsgBase
        '''
        if isinstance(obj, MsgBase) is False:
            raise TypeError('obj should be an instance of MsgBase')
        tid = obj.GetTypeId().to_bytes(AppSerializer.TID_SIZE, byteorder=sys.byteorder, signed=False)
        bt = obj.serialize()
        length = len(bt).to_bytes(AppSerializer.LEN_SIZE, byteorder=sys.byteorder, signed=False)
        checksum = hashlib.blake2b(tid + length + bt, digest_size=AppSerializer.DIGEST_SIZE).digest()
        return tid + length + bt + checksum # concat
    def deserialize(self, bt):
        '''
        return [(typeId, bytes), ...] (may be empty)
        its state may change during to process of parsing bytes
        raise RuntimeError if checksum check is failed
        '''
        self.buffer += bt
        # parse as many as possible
        ret = []
        parsedAny = True
        parseHead = 0
        parseTail = len(self.buffer)
        while parsedAny is True:
            parsedAny = False
            # TID field is parsed
            if self.state == AppSerializerState.TID and (parseTail - parseHead) >= AppSerializer.TID_SIZE:
                self.stateTid = int.from_bytes(self.buffer[parseHead : parseHead + AppSerializer.TID_SIZE], byteorder=sys.byteorder, signed=False)
                parseHead += AppSerializer.TID_SIZE
                self.state = AppSerializerState.LEN
                if MOUDLE_DEBUG:
                    print(f'Finish parsing TID {self.stateTid}')
            # LEN field is parsed
            if self.state == AppSerializerState.LEN and (parseTail - parseHead) >= AppSerializer.LEN_SIZE:
                self.stateLen = int.from_bytes(self.buffer[parseHead : parseHead + AppSerializer.LEN_SIZE], byteorder=sys.byteorder, signed=False)
                parseHead += AppSerializer.LEN_SIZE
                self.state = AppSerializerState.DATA
                if MOUDLE_DEBUG:
                    print(f'Finish parsing LEN {self.stateLen}')
            # DATA field is parsed
            if self.state == AppSerializerState.DATA and (parseTail - parseHead) >= self.stateLen:
                self.stateData = self.buffer[parseHead : parseHead + self.stateLen]
                parseHead += self.stateLen
                self.state = AppSerializerState.CHECKSUM
                if MOUDLE_DEBUG:
                    print(f'Finish parsing DATA {self.stateData}')
            if self.state == AppSerializerState.CHECKSUM and (parseTail - parseHead) >= AppSerializer.DIGEST_SIZE:
                checksum = self.buffer[parseHead : parseHead + AppSerializer.DIGEST_SIZE]
                parseHead += AppSerializer.DIGEST_SIZE
                tid = self.stateTid.to_bytes(AppSerializer.TID_SIZE, byteorder=sys.byteorder, signed=False)
                length = self.stateLen.to_bytes(AppSerializer.LEN_SIZE, byteorder=sys.byteorder, signed=False)
                correctChecksum = hashlib.blake2b(tid + length + self.stateData, digest_size=AppSerializer.DIGEST_SIZE).digest()
                if True:
                    ret.append((self.stateTid, self.stateData))
                    self.state = AppSerializerState.TID
                    parsedAny = True
                    if MOUDLE_DEBUG:
                        print(f'Finish parsing CHECKSUM {checksum}')
                else:
                    raise RuntimeError(f'Checksum error, expect:{correctChecksum} but got {checksum}')
        if parseHead != 0:
            self.buffer = self.buffer[parseHead:]
        return ret