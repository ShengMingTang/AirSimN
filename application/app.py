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
import subprocess as sp
import shlex
# custom imports
import detect

# convert screen recorder to visible format
# fmpeg -i in.mp4 -pix_fmt yuv420p -c:a copy -movflags +faststart out.mp4
# convert image to video
# ffmpeg -r FPS -i WORK_DIR/img%d.png -vcodec libx264 -crf 15  -pix_fmt yuv420p out.mp4

# bottleneck finders
PHOTO_TAKEN=True # take photo or not
TO_TRANS=True # True then UAV will trans images
WRITE_PIPE='pipe' # 'hdd' | 'ssd' | 'pipe' , to write to disk or send pipeline to ffmpeg
# log
# PHOTO_TAKEN TO_TRANS FPS WRITE_OR_PIPE CAMERA -> nsTotal, AirSimTotal, , #comment
# False, False, 5, write, LD, -> 28.9, 35.5
# True, False, 5, write, LD, -> 31.0, 35.5
# True, True, 5, write, LD, -> 43.15, 36.7
# True, True, 5, pipe, LD, -> 43.08, 36.5
# True, False, 5, write, SD, -> 22.2, 35.5
# True, True, 5, write, SD, -> 420, 52
# True, True, 5, pipe, SD, -> 416, 52

# UETxPower=30
# True, True, 5, pipe, SD, -> 412, 52

# UETxPower=30, tcp seg size=30000
# True, True, 5, pipe, SD, -> 96, 48

TASK = 'path' # 'wind' | 'path' | 'throughput
FPS = 10
EXP_NAME ='exp_all'
WORK_DIR = Path(os.getcwd())/'..'/'settings'/EXP_NAME
CAMERA = 'SD' # 'LD' | 'SD' | 'HD'
IMG_DIR = WORK_DIR/f'pic_{CAMERA}'
OUT_MP4 = WORK_DIR/f'out{CAMERA}.mp4'
WIDTH = {'LD':256, 'SD':720}[CAMERA]
HEIGHT = {'LD':144, 'SD':576}[CAMERA]

class UavApp(UavAppBase):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.mutex = threading.Lock()
        self.stop = False
        self.recThread = threading.Thread(target=UavApp.recorder, args=(self,1/FPS, 10))
    def recorder(self, period, maxSize):
        stop = False
        client = airsim.MultirotorClient()
        lastFlows = []
        while stop is False:
            if PHOTO_TAKEN:
                with Ctrl.Frozen():
                    rawImage = client.simGetImage(CAMERA, airsim.ImageType.Scene, vehicle_name=self.name)
                    t = Ctrl.GetSimTime()
            if TO_TRANS:
                msg = MsgImg(rawImage, t)
                f = self.createFlow(msg)
                lastFlows.append(f)
                if len(lastFlows) == 1:
                    lastFlows[0].start()
                elif lastFlows[0].isDone(): # try to send next
                    lastFlows = lastFlows[1:]
                    if len(lastFlows) > 0:
                        lastFlows[0].start()
                else: # downsample
                    print(f'{self.name} down sampled')
                    lastFlows = lastFlows[::2]
                Ctrl.WaitUntil(msg.timestamp + period)
            else:
                Ctrl.Wait(period)
            with self.mutex:
                stop = self.stop
        msg = MsgRaw(b'bye')
        self.Tx(msg)
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
            msg = MsgRaw(b'bye')
            self.Tx(msg)
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
        self.customfn(*args, **kwargs)
        print(f'{self.name} joined')
        
class GcsApp(GcsAppBase):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        # any self.attribute that you need
        self.queue = queue.Queue()
    def pathfollower(self):
        print('***********************')
        print(f'Current Working dir {WORK_DIR}')
        cmd = f'ffmpeg -y -s {WIDTH}x{HEIGHT} -pixel_format bgr24 -f rawvideo -r {FPS} -i pipe: -vcodec libx265 -pix_fmt yuv420p -crf 24 {OUT_MP4}'
        print(f'Using cmd: {cmd}')
        process = sp.Popen(shlex.split(cmd), stdin=sp.PIPE)
        print('***********************')
        opt = detect.loadDefaultOpt()
        model = detect.loadModel(opt)
        
        log = open(str(WORK_DIR/'log.txt'), 'w')
        writer = csv.writer(log)
        writer.writerow(['time', 'filename', 'src'])
        
        if WRITE_PIPE != 'pipe':
            count = 0
            Path.mkdir(IMG_DIR, exist_ok=True)
            self.timeDiskwrite=0
        
        lastImg = MsgImg(np.zeros((144, 256, 3), dtype=np.uint8))
        thisImg = MsgImg(np.zeros((144, 256, 3), dtype=np.uint8))
        
        T = 1/FPS
        Ctrl.Wait(2.0)
        while Ctrl.ShouldContinue():
            reply = 1
            while reply is not None:
                reply = self.Rx()
                if reply is not None:
                    name, reply = reply
                    if isinstance(reply, MsgRaw): # possibly a goodbye message
                        print(f'{self.name} recv {reply.data}')
                        Ctrl.SetEndTime(Ctrl.GetSimTime() + 5.0) # end of simulation
                    else:
                        thisImg = reply
                        print(f'{self.name} rcv img at time:{thisImg.timestamp}')
                        thisImg.png = cv2.imdecode(airsim.string_to_uint8_array(thisImg.png), cv2.IMREAD_UNCHANGED)
                        thisImg.png = cv2.cvtColor(thisImg.png, cv2.COLOR_BGRA2BGR)
                        thisImg.png, allboxes = detect.detectYolo(model, thisImg.png, opt)
                        
                        if lastImg.timestamp == 0:
                            lastImg = thisImg
                        else:
                            while abs(lastImg.timestamp + T - thisImg.timestamp) > T/5: # drift error
                                lastImg.timestamp += T
                                if WRITE_PIPE != 'pipe':
                                    t0 = time.time()
                                    cv2.imwrite(str(IMG_DIR/('img%d.png'%(count))), lastImg.png)
                                    self.timeDiskwrite += (time.time() - t0)
                                    writer.writerow([lastImg.timestamp, 'img%d.png'%(count), 'pad'])
                                    count += 1
                                else:
                                    print(f'{self.name} pad img at t={lastImg.timestamp}')
                                    process.stdin.write(lastImg.png)
                                    
                    if WRITE_PIPE != 'pipe':
                        t0 = time.time()
                        cv2.imwrite(str(IMG_DIR/('img%d.png'%(count))), thisImg.png)
                        self.timeDiskwrite += (time.time() - t0)
                        writer.writerow([thisImg.timestamp, 'img%d.png'%(count), 'photo'])
                        count += 1
                    else:
                        process.stdin.write(thisImg.png)
                
                lastImg = thisImg
            Ctrl.Wait(T)
        log.close()
        
        if WRITE_PIPE != 'pipe':
            print(f'{self.name} spent {self.timeDiskwrite} on disk write')
        
        process.stdin.close()
        # Wait for sub-process to finish
        process.wait()
        # Terminate the sub-process
        process.terminate()
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
        self.Tx(rep, 'B')
        self.Tx(rep, 'B')
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
        self.customfn(*args, **kwargs)
        print(f'{self.name} joined')