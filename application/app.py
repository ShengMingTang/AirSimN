from appBase import *
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
        
    def customfn(self, *args, **kwargs):
        # as your new target function
        pass

    # def run(self, *args, **kwargs):
    #     self.beforeRun()
    #     self.customfn(*args, **kwargs)
    #     self.afterRun()
    #     print(f'{self.name} joined')
        
class GcsApp(GcsAppBase):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        # any self.attribute that you need
        
    def customfn(self, *args, **kwargs):
        # as your new target function
        pass

    # def run(self, *args, **kwargs):
    #     self.beforeRun()
    #     self.customfn(*args, **kwargs)
    #     self.afterRun()
    #     print(f'{self.name} joined')