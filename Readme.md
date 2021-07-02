# AirSimN
## Install pre-requisites

### Clone this repo

You may fork this and substitute the following cloned url
```shell
$ cd
$ git clone --recurse-submodules https://github.com/ShengMingTang/AirSimN.git
```

### Install ZMQ
```shell
# https://github.com/zeromq/libzmq#example-debian-9-latest-release-no-draft-apis
$ wget https://download.opensuse.org/repositories/network:/messaging:/zeromq:/release-stable/Debian_9.0/Release.key -O- | sudo apt-key add
$ sudo apt-get install libzmq3-dev
```
### Download Unreal Environment
https://github.com/microsoft/AirSim/releases/tag/v1.5.0-linux\
Choose AirSimNH and extract it to the current folder
---

## Compile AirSimN and run self-test
```shell
$ cd AirSimN
$ sh setup.sh # load all compressed files then compile

$ sh run.sh settings/selftest.json
```
output will be stored at log

---

### Run
```shell
sh run.sh path_to_setting.json
```
---

## Directory tree
.\
|-- AirSim <span style="color:yellow">(AirSim submodule)</span>\
|-- ns-allinone-3.32 <span style="color:yellow">(ns-3 source after decompression)</span>\
|-- AirSimNH <span style="color:yellow">(AirSimNH environment after decompression)</span>\
|-- application <span style="color:yellow">(python application code)</span>\
|-- network <span style="color:yellow">(ns3 source code, referenced in ns-3 source directory)</span>\
|-- settings <span style="color:yellow">(bank of settings.json)</span>\
|-- compressed <span style="color:yellow">(backup compressed files)</span>\
|-- log <span style="color:yellow">(store log generated at run time)</span>

---

## How to augment settings.json
Add these keys to **first level** of your settings.json, main program will parse this and configure ns-3 topology

Note that you need to **reload AirSim** if you modifiy something related to AirSim configuration (for example, the number of drones)
> * There is no default value for **"Vehicles"**. You should specify this explicitly!
> * Name of each UAV must not contain any white space or 'GCS'

``` json
// default values in settings.json except for "Vehicles"
{
// ... others
"Vehicles": {
    "A": {
        "VehicleType": "SimpleFlight",
        "X": 0,
        "Y": 0,
        "Z": 0,
        "EnableTrace": true,
        "Cameras" : {
            "high_res": {
                "CaptureSettings" : [
                    {
                        "ImageType" : 0,
                        "Width" : 1920,
                        "Height" : 1080
                    }
                ],
                "X": 0.50, "Y": 0.00, "Z": 0.00,
                "Pitch": 0.0, "Roll": 0.0, "Yaw": 0.0
            }
        }
    }
},

"updateGranularity": 0.01,

"segmentSize": 1448,
"numOfCong": 0,
"congRate": 1.0,
"congArea": [0, 0, 10],

"initEnbApPos": [
    [0, 0, 0]
],

"nRbs": 6,
"TcpSndBufSize": 71680,
"TcpRcvBufSize": 71680,
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

"endTime": math.inf
}
```
* **updateGranularity**: <font color="blue">float</font>, control quality of simulation
* **segmentSize**: <font color="blue">int</font>, TCP socket segmentsize
* **numOfCong**: <font color="blue">int</font>, the number of background traffic
* **congRate**: <font color="blue">float</font>, congestion node will transmit packet in period of 1/congRate
* **congArea**: <font color="blue">\[x(float), y(float), r(float)]</font>, congestion node will randomly walk in circle of radius r centered at (x, y)
* **initEnbApPos**: <font color="blue">\[\[float, float, float], ...]</font>, *list of list of 3 floats*, specify postiion of each EnbNode(LTE) or ApNode(Wifi), each 3-float list will be interpreted as \[x, y, z] in 3D coordinate
* **nRbs**: <font color="blue">int</font>, the number of resource blocks. (This only takes on some specific values, see appendix)
* **TcpSndBufSize**: <font color="blue">int (max 0:4294967295)</font>, TCP sender buffer size
* **TcpRcvBufSize**: <font color="blue">int (max 0:4294967295)</font>, TCP receiver buffer size
* **CqiTimerThreshold**: *10*,
* **LteTxPower**: *0*,
* **p2pDataRate**: <font color="blue">string</font>, in "\<number><G|M>b/s"
* **p2pMtu**: <font color="blue">int</font>, GCS segment size
* **p2pDelay**: <font color="blue">float</font> in seconds, GCS channel delay
* **useWifi**: <font color="blue">0/1</font>, whether to use Wifi setting, value 0 will use LTE.
* **isMainLogEnabled**: <font color="blue">0/1</font>, main loggging enabled
* **isGcsLogEnabled**: <font color="blue">0/1</font>, GCS loggging enabled
* **isUavLogEnabled**: <font color="blue">0/1</font>, UAV loggging enabled
* **isCongLogEnabled**: <font color="blue">0/1</font>, congestion node loggging enabled
* **isSyncLogEnabled**: <font color="blue">0/1</font>, synchronization loggging enabled
* **endTime**: <font color="blue">float</font>, specify how many seconds we are going to simulate (I would rather not specify this)
---
## How to implement your own application (in ./application)
Make sure that you set up setup_path.py correctly, please refer to [this](https://hackmd.io/_47KEwwwRu6TZkeyWJm07A?view#How-to-run-custom-code-Python)
The only files you will possibly write on are
1. app.py (to implement your specific task)
2. msg.py (to implement your own message)
---

### Simulation Clock Management API
In ctrl.py, there is a class *ctrl* which provides us with several simulation clock managment
* **Ctrl.Wait(nsec, cb)**: selay nsec seconds, blocked until time is expired, cb() is fired (with no arguments) is provided
* **Ctrl.WaitUntil(time, cb)**: similar to Ctrl.Wait() but this wait for an absolute time point
* **Ctrl.SetEndTime(when)**: set when this simulation should end in absolute simulation time. You will call this when your tasks are all done especially "endTime" is not specified in settings.json.
* **Ctrl.GetSimTime()**: get the current simulation time in second(s) as float
* **Ctrl.ShouldContinue()**: return bool to indicate that simulation clock is still maintained or not. Usually you will use this in an infinite while loop.
* **Ctrl.Frozen()**: context manager for freeze the simulation clock
    > This is mainly used for compensating for extra work done for simulation. For example, client.simGetImage(...) may require much work than in reality. The simulation clock must be frozen to keep elapsed time correct.
``` python
# For poll is the simulation is over
while Ctrl.ShouldContinue():
    # Do whatever you want
    pass

# Freeze the simulation clock
with Ctrl.Frozen():
    # Do whatever you want
    pass
```
---

### Application Code Hierarachy
![](https://i.imgur.com/Of6nlkF.png)
In app.py,  set up your custom task
``` Python
import setup_path
import airsim
from appBase import *
from msg import *
from ctrl import *
'''
Custom App code
'''
class UavApp(UavAppBase):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        # any self.attribute that you need
    def run(self, *args, **kwargs):
        return super().run(*args, **kwargs)
        # or implement your task
        
        
class GcsApp(GcsAppBase):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        # any self.attribute that you need
    def run(self, *args, **kwargs):
        return super().run(*args, **kwargs)
        # or implement your task

```
A ready-to-run example is at **mpeg-demo** branch

---

### Message Hierarchy
![](https://i.imgur.com/8EpR7SP.png)
Refer to appProtocolBase.py, implement your customMsg in msg.py. Here is the guideline. MsgRaw and MsgImg are available to use. TypeId will be checked at runtime, raise error if ID collision occurrs.
``` Python
class YourMsg(MsgBase):
    def __init__(self, data=bytes(0), **kwargs):
        # your desired data field
        
    @classmethod
    def GetTypeId(self):
        # return an unique ID of this Msg ranging in [3,255]
        return 255 # as long as this is unique
    def serialize(self):
        # return bytes
        # You can use picke.dumps(self) if you don't care about efficiency
        return pickle.dumps(self)
        
    @classmethod
    def Deserialize(cls, data):
        # return this kind of object
        # You can use picke.loads(self) if you don't care about efficiency
        return pickle.loads(self)
        
    def __str__(self):
        # return string representation of this object
```

---

### The Flow Class
Flow is the basic transmission unit of a pair of sender and receiver. This store some neccessary information about the whole transmission and enables high performance in NS.
* **Flow.isStarted()**: returns bool to indicate it is started or not
* **Flow.isDone()**: returns bool to indicate the flow is completed or not

---

### The Router Class

Router is for routing flow between py application and NS application. This enables fast message transmission instead of tedious data copying.
Router interfacts heavily with the Flow class.

---

### Application Level Message Exchange
![](https://i.imgur.com/ggVBwGT.png)
Args:
* msg:
    1. MsgBase-like object or any object that supports len()
    2. iterable of objects mentioned above
* toName: 
    1. to specify the target receiver in string (keys in "Vehicles" in setting.json)
    2. default to 'GCS' for UavApp

In UavApp or GcsApp,
* **self.Tx(msg, toName)**: this will start transmitting msg to toName immediately and cannot be stopped or interrupted later.
* **self.createFlow(msg, toName)**: this will create a flow object between the caller and ther receiver.
```Python
# For example, in UavApp
f = self.createFlow(msg)
# flow is just created not started
f.start() # start the flow
```