import setup_path
import airsim
from appBase import *
from msg import *
from ctrl import *
import os
'''
Custom App code
'''
import threading
from pathlib import Path
import cv2
import csv

import detect

# fmpeg -i in.mp4 -pix_fmt yuv420p -c:a copy -movflags +faststart out.mp4

FPS = 10
EXP_NAME ='exp_test'
WORK_DIR = Path(os.getcwd())/'..'/'settings'/EXP_NAME
IMG_DIR = WORK_DIR/'pic'
TASK = 'path' # 'wind' | 'path' | 'throughput
CAMERA = 'LD' # 'LD' | 'SD' | 'HD
# ffmpeg -r FPS -i WORK_DIR/img%d.png -vcodec libx264 -crf 15  -pix_fmt yuv420p out.mp4

class UavApp(UavAppBase):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.mutex = threading.Lock()
        self.stop = False
        self.recThread = threading.Thread(target=UavApp.recorder, args=(self,1/FPS, 10))
    def recorder(self, period, maxSize):
        heap = []
        stop = False
        client = airsim.MultirotorClient()
        while stop is False:
            heap = heap[-maxSize+1:]
            Ctrl.Freeze(True)
            rawImage = client.simGetImage(CAMERA, airsim.ImageType.Scene, vehicle_name=self.name)
            Ctrl.Freeze(False)
            
            t = Ctrl.GetSimTime()
            msg = MsgImg(rawImage, t)
            heap.append(msg)
            # ress = self.Tx(heap) # transmit as much as it can
            ress = self.Tx(msg)
            ress = [ress]
            head = 0
            print(f'Shot at time: {t}, {ress}')
            for res in ress:
                if res >= 0:
                    head += 1
                else:
                    break
            heap = heap[head:]
            t = Ctrl.GetSimTime()
            Ctrl.WaitUntil(msg.timestamp + period)
            with self.mutex:
                stop = self.stop
        msg = MsgRaw(b'bye')
        res = self.Tx(msg)
        while res < 0:
            res = self.Tx(msg)
        print(f'{self.name} says bye')
    def pathfollower(self):
        # SD: 720x576 size 721637
        # HD: 1920x1080 size 3377913
        client = airsim.MultirotorClient()
        client.enableApiControl(True, vehicle_name=self.name)
        client.armDisarm(True, vehicle_name=self.name)
        Ctrl.Wait(1.0)
        self.recThread.start()
        with open(WORK_DIR/'path.csv') as f:
            rows = csv.reader(f)
            headers = next(rows)
            for i, row in enumerate(rows):
                ty = row[0]
                if ty == 'pos':
                    x, y, z, vel = [float(item) for item in row[1:]]
                    print(f'{self.name} goes to {x},{y}, {z}')
                    client.moveToPositionAsync(x, y, z, vel, vehicle_name=self.name).join()
                    print(f'{self.name} arrives at {x},{y}, {z}')
                elif ty == 'yaw':
                    yaw = float(row[1])
                    client.rotateToYawAsync(yaw).join()
                else:
                    raise ValueError(f'Unrecongnized op {ty}')
        client.landAsync().join()
        with self.mutex:
            self.stop = True
        self.recThread.join()
    def windEffect(self):
        if self.name == 'A':
            client = airsim.MultirotorClient()
            client.enableApiControl(True, vehicle_name=self.name)
            client.armDisarm(True, vehicle_name=self.name)
            client.simSetTraceLine([1,0,1], thickness=3.0)
            client.takeoffAsync(vehicle_name=self.name).join()
            client.moveToPositionAsync(20, 0, -3, 7, vehicle_name=self.name).join()
            client.hoverAsync().join()
            client.simSetTraceLine([1,1,0], thickness=3.0)
            client.moveToPositionAsync(0, 0, -0.5, 7, vehicle_name=self.name).join()
            client.hoverAsync().join()
            client.landAsync(vehicle_name=self.name).join()
            res = -1
            msg = MsgRaw(b'bye')
            while res < 0:
                res = self.Tx(msg)
                Ctrl.Wait(0.5)
            print(f'{self.name} finished')
        elif self.name == 'B':
            Ctrl.Wait(1.0)
            res = self.Rx()
            while Ctrl.ShouldContinue() and res is None:
                res = self.Rx()
                Ctrl.Wait(0.5)
            print(f'{self.name} recv GO')
            client = airsim.MultirotorClient()
            client.enableApiControl(True, vehicle_name=self.name)
            client.armDisarm(True, vehicle_name=self.name)
            client.simSetTraceLine([1,0,1], thickness=3.0)
            client.takeoffAsync(vehicle_name=self.name).join()
            client.moveToPositionAsync(20, -3, -3, 7, vehicle_name=self.name).join()
            client.simSetTraceLine([1,1,0], thickness=3.0)
            client.moveToPositionAsync(0, -3, -0.5, 7, vehicle_name=self.name).join()
            client.hoverAsync().join()
            client.landAsync(vehicle_name=self.name).join()
            Ctrl.SetEndTime(Ctrl.GetSimTime() + 1.0)
    def customfn(self, *args, **kwargs):
        if TASK == 'wind':
            self.windEffect()
        elif TASK == 'path':
            self.pathfollower()
        elif TASK == 'throughput':
            self.staticThroughputTest(0, 0.01)
    def run(self, *args, **kwargs):
        self.beforeRun()
        self.customfn(*args, **kwargs)
        self.afterRun()
        print(f'{self.name} joined')
        
class GcsApp(GcsAppBase):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        # any self.attribute that you need
    def pathfollower(self):
        print('***********************')
        print(f'Current Working dir {WORK_DIR}')
        print('***********************')
        opt = detect.loadDefaultOpt()
        model = detect.loadModel(opt)
        
        Path.mkdir(IMG_DIR, exist_ok=True)
        log = open(str(WORK_DIR/'log.txt'), 'w')
        writer = csv.writer(log)
        writer.writerow(['time', 'filename', 'src'])
        
        count = 0
        lastImg = MsgImg(np.zeros((144, 256, 3), dtype=np.uint8))
        thisImg = MsgImg(np.zeros((144, 256, 3), dtype=np.uint8))
        
        T = 1/FPS
        Ctrl.Wait(2.0)
        while Ctrl.ShouldContinue():
            reply = self.Rx()
            if reply is not None:
                name, reply = reply
                if isinstance(reply, MsgRaw): # possibly a goodbye message
                    print(f'{self.name} recv {reply.data}')
                    Ctrl.SetEndTime(Ctrl.GetSimTime() + 5.0) # end of simulation
                else:
                    thisImg = reply
                    print(f'{self.name} rcv img at time:{thisImg.timestamp}')
                    if lastImg.timestamp == 0:
                        lastImg = thisImg
                    thisImg.png = cv2.imdecode(airsim.string_to_uint8_array(thisImg.png), cv2.IMREAD_UNCHANGED)
                    thisImg.png = cv2.cvtColor(thisImg.png, cv2.COLOR_BGRA2BGR)
                    thisImg.png, allboxes = detect.detectYolo(model, thisImg.png, opt)
                # @@ assume timestamp is regular, no much drift
                cv2.imwrite(str(IMG_DIR/('img%d.png'%(count))), thisImg.png)
                count += 1
                lastImg = thisImg
                writer.writerow([thisImg.timestamp, 'img%d.png'%(count), 'photo'])
                print(f'GCS src, count={count}')
            Ctrl.Wait(T)
        log.close()
    def windEffect(self):
        client = airsim.MultirotorClient()
        client.simSetWind(airsim.Vector3r(0,0,0))
        Ctrl.Wait(1.0)
        rep = self.Rx()
        while Ctrl.ShouldContinue() and rep is None:
            rep = self.Rx()
            Ctrl.Wait(0.5)
        print(f'{self.name} set wind!')
        name, rep = rep
        y = 15
        res = self.Tx(rep, 'B')
        while res < 0:
            res = self.Tx(rep, 'B')
            Ctrl.Wait(0.5)
        print(f'{self.name} notifies B')
        while Ctrl.ShouldContinue():
            w = airsim.Vector3r(0, y, 0)
            y *= -1
            client.simSetWind(w)
            Ctrl.Wait(1.0)
        client.simPause(False)          
    def customfn(self, *args, **kwargs):
        if TASK == 'wind':
            self.windEffect()
        elif TASK == 'path':
            self.pathfollower()
        elif TASK == 'throughput':
            self.staticThroughputTest(0, 0.01)
    def run(self, *args, **kwargs):
        self.beforeRun()
        self.customfn(*args, **kwargs)
        self.afterRun()
        print(f'{self.name} joined')
