import zmq
import sys
from pathlib import Path
import matplotlib.pyplot as plt
import argparse

# custom import 
from app import GcsApp, UavApp
from msg import *
from ctrl import *

# check an Unreal Env has been set up
import setup_path
import airsim

if __name__ == '__main__':    
    try:
        client = airsim.MultirotorClient()
        client.confirmConnection()
    except:
        sys.exit()
        
    json_path = Path.home()/'Documents'/'AirSim'/'settings.json'

    context = zmq.Context()
    ctrlThread = Ctrl(context)
    netConfig = ctrlThread.sendNetConfig(json_path)


    gcsThread = GcsApp(context=context)
    uavsThread = [ UavApp(name=name, iden=i, context=context) for i, name in enumerate(netConfig['uavsName']) ]

    ctrlThread.waitForSyncStart()

    # NS will wait until AirSim sends back something from now on

    ctrlThread.start()
    # gcsThread.start()
    for td in uavsThread:
        td.start()      
    gcsThread.run()

    ctrlThread.join()
    # gcsThread.join()
    for td in uavsThread:
        td.join()

    plt.clf()
    sys.exit()