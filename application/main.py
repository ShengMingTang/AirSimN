import sys
from pathlib import Path
import matplotlib.pyplot as plt
import argparse

# custom import 
from app import GcsApp, UavApp
from msg import *
from ctrl import *
from router import mainRouter, context

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
    
    ctrlThread = Ctrl(context)
    netConfig = ctrlThread.sendNetConfig(json_path)


    gcsThread = GcsApp(name='GCS')
    gcsEndPoint = mainRouter.register('GCS', AIRSIM2NS_GCS_PORT_START)
    uavsThread = [ UavApp(name=name) for i, name in enumerate(netConfig['uavsName']) ]
    endPoints = [mainRouter.register(name, AIRSIM2NS_UAV_PORT_START+i) for i, name in enumerate(netConfig['uavsName']) ]

    mainRouter.compile()

    ctrlThread.waitForSyncStart()
    # NS will wait until AirSim sends back something from now on

    mainRouter.start()
    ctrlThread.start()
    for td in uavsThread:
        td.start()
    # GCS run in the main thread for plotting   
    gcsThread.run()

    # End of simulation
    mainRouter.join()
    ctrlThread.join()
    for td in uavsThread:
        td.join()
    sys.exit()
