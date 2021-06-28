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
    # def run(self, *args, **kwargs):
        # return super().run(*args, **kwargs)
        # or implement your task
        
        
class GcsApp(GcsAppBase):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        # any self.attribute that you need
    # def run(self, *args, **kwargs):
        # return super().run(*args, **kwargs)
        # or implement your task
