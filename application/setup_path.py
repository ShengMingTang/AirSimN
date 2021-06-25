# Import this module to automatically setup path to local airsim module
# This module first tries to see if airsim module is installed via pip
# If it does then we don't do anything else
# Else we look up grand-parent folder to see if it has airsim folder
#    and if it does then we add that in sys.path

import os,sys,logging

def insertPath():
    path = '../AirSim/PythonClient/'
    airsim_path = os.path.join(path, 'airsim')
    client_path = os.path.join(airsim_path, 'client.py')
    if os.path.exists(client_path):
        sys.path.insert(0, path)
    else:
        logging.warning("airsim module not found in parent folder. Using installed package (pip install airsim).")
        
insertPath()