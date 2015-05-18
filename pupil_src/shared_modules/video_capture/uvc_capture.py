'''
(*)~----------------------------------------------------------------------------------
 Pupil - eye tracking platform
 Copyright (C) 2012-2015  Pupil Labs

 Distributed under the terms of the CC BY-NC-SA License.
 License details are in the file license.txt, distributed as part of this software.
----------------------------------------------------------------------------------~(*)
'''

import uvc
from uvc import device_list
#check versions for our own depedencies as they are fast-changing
assert uvc.__version__ >= '0.1'

from ctypes import c_double
from pyglui import ui
from time import time
#logging
import logging
logger = logging.getLogger(__name__)

class CameraCaptureError(Exception):
    """General Exception for this module"""
    def __init__(self, arg):
        super(CameraCaptureError, self).__init__()
        self.arg = arg



class Camera_Capture(object):
    """
    Camera Capture is a class that encapsualtes uvc.Capture:
     - adds UI elements
     - adds timestamping sanitization fns.
    """
    def __init__(self,uid,timebase=None):
        self.uid = uid
        if timebase == None:
            logger.debug("Capture will run with default system timebase")
            self.timebase = c_double(0)
        elif hasattr(timebase,'value'):
            logger.debug("Capture will run with app wide adjustable timebase")
            self.timebase = timebase
        else:
            logger.error("Invalid timebase variable type. Will use default system timebase")
            self.timebase = c_double(0)

        # self.use_hw_ts = self.check_hw_ts_support()
        self.use_hw_ts = False
        self._last_timestamp = self.get_now()

        self.capture = uvc.Capture(uid)
        logger.debug('avaible modes %s'%self.capture.avaible_modes)

        # self.controls = self.capture.enum_controls()
        self.controls = []
        # controls_dict = dict([(c['name'],c) for c in self.controls])
        # try:
        #     self.capture.set_control(controls_dict['Focus, Auto']['id'], 0)
        # except KeyError:
        #     pass
        # try:
        #     # exposure_auto_priority == 1
        #     # leads to reduced framerates under low light and corrupt timestamps.
        #     self.capture.set_control(controls_dict['Exposure, Auto Priority']['id'], 0)
        # except KeyError:
        #     pass

        self.sidebar = None
        self.menu = None


    def check_hw_ts_support(self):
        # hw timestamping:
        # uvc supports Sart of Exposure hardware timestamping ofr UVC Capture devices
        # these HW timestamps are excellent referece times and
        # preferred over softwaretimestamp denoting the avaibleilt of frames to the user.
        # however not all uvc cameras report valid hw timestamps, notably microsoft hd-6000
        # becasue all used devices need to properly implement hw timestamping for it to be usefull
        # but we cannot now what device the other process is using  + the user may select a differet capture device during runtime
        # we use some fuzzy logic to determine if hw timestamping should be employed.

        blacklist = ["Microsoft","HD-6000"]
        qualifying_devices = ["C930e","Integrated Camera", "USB 2.0 Camera"]
        attached_devices = [c.name for c in device_list()]
        if any(qd in self.name for qd in qualifying_devices):
            use_hw_ts = True
            logger.info("Capture device: '%s' supports HW timestamping. Using hardware timestamps." %self.name)
        else:
            use_hw_ts = False
            logger.info("Capture device: '%s' is not known to support HW timestamping. Using software timestamps." %self.name)

        for d in attached_devices:
            if any(bd in d for bd in blacklist):
                logger.info("Capture device: '%s' detected as attached device. Falling back to software timestamps"%d)
                use_hw_ts = False
        return use_hw_ts

    def re_init(self,uid,size=(640,480),fps=30):

        current_size = self.capture.frame_size
        current_fps = self.capture.frame_rate

        self.capture = None
        #recreate the bar with new values
        self.deinit_gui()

        # self.use_hw_ts = self.check_hw_ts_support()
        self.use_hw_ts = False
        self.capture = uvc.Capture(uid)
        self.capture.frame_size = current_size
        self.capture.frame_rate = current_fps
        # self.controls = self.capture.enum_controls()
        # controls_dict = dict([(c['name'],c) for c in self.controls])
        # try:
        #     self.capture.set_control(controls_dict['Focus, Auto']['id'], 0)
        # except KeyError:
        #     pass
        # try:
        #     # exposure_auto_priority == 1
        #     # leads to reduced framerates under low light and corrupt timestamps.
        #     self.capture.set_control(controls_dict['Exposure, Auto Priority']['id'], 0)
        # except KeyError:
        #     pass

        self.init_gui(self.sidebar)



    def get_frame(self):
        try:
            frame = self.capture.get_frame_robust()
        except:
            raise CameraCaptureError("Could not get frame from %s"%self.uid)

        timestamp = frame.timestamp
        if self.use_hw_ts:
            # lets make sure this timestamps is sane:
            if abs(timestamp-uvc.get_sys_time_monotonic()) > 2: #hw_timestamp more than 2secs away from now?
                logger.warning("Hardware timestamp from %s is reported to be %s but monotonic time is %s"%('/dev/video'+str(self.src_id),timestamp,uvc.get_sys_time_monotonic()))
                timestamp = uvc.get_sys_time_monotonic()
        else:
            # timestamp = uvc.get_sys_time_monotonic()
            timestamp = self.get_now()

        timestamp -= self.timebase.value
        frame.timestamp = timestamp
        return frame

    def get_now(self):
        return time()

    @property
    def frame_rate(self):
        return self.capture.frame_rate
    @frame_rate.setter
    def frame_rate(self,new_rate):
        #closest match for rate
        rates = [ abs(r-new_rate) for r in self.capture.frame_rates ]
        best_rate_idx = rates.index(min(rates))
        rate = self.capture.frame_rates[best_rate_idx]
        if rate != new_rate:
            logger.warning("%sfps capture mode not available at (%s) on '%s'. Selected %sfps. "%(new_rate,self.capture.frame_size,self.capture.name,rate))
        self.capture.frame_rate = rate

    @property
    def frame_size(self):
        return self.capture.frame_size
    @frame_size.setter
    def frame_size(self,new_size):
        self.capture.frame_size = filter_sizes(self.name,new_size)

    @property
    def name(self):
        return self.capture.name

    def init_gui(self,sidebar):


        # #lets define some  helper functions:
        # def gui_load_defaults():
        #     for c in self.controls:
        #         if not c['disabled']:
        #             self.capture.set_control(c['id'],c['default'])
        #             c['value'] = self.capture.get_control(c['id'])

        # def gui_update_from_device():
        #     for c in self.controls:
        #         if not c['disabled']:
        #             c['value'] = self.capture.get_control(c['id'])


        def gui_get_frame_rate():
            return self.capture.frame_rate

        def gui_set_frame_rate(rate):
            self.capture.frame_rate = rate

        def gui_init_cam_by_uid(requested_id):
            for cam in uvc.device_list():
                if cam['uid'] == requested_id:
                    self.re_init(requested_id)
                    return
            logger.warning("could not reinit capture, src_id not valid anymore")
            return

        #create the menu entry
        self.menu = ui.Growing_Menu(label='Camera Settings')
        cameras = uvc.device_list()
        camera_names = [c['name'] for c in cameras]
        camera_ids = [c['uid'] for c in cameras]
        self.menu.append(ui.Selector('uid',self,selection=camera_ids,labels=camera_names,label='Capture Device', setter=gui_init_cam_by_uid) )

        hardware_ts_switch = ui.Switch('use_hw_ts',self,label='use hardware timestamps')
        hardware_ts_switch.read_only = True
        self.menu.append(hardware_ts_switch)

        self.menu.append(ui.Selector('frame_rate', selection=self.capture.frame_rates,label='Frames per second', getter=gui_get_frame_rate, setter=gui_set_frame_rate) )


        for control in self.controls:
            c = None
            ctl_name = control['name']

            # we use closures as setters and getters for each control element
            def make_setter(control):
                def fn(val):
                    self.capture.set_control(control['id'],val)
                    control['value'] = self.capture.get_control(control['id'])
                return fn
            def make_getter(control):
                def fn():
                    return control['value']
                return fn
            set_ctl = make_setter(control)
            get_ctl = make_getter(control)

            #now we add controls
            if control['type']=='bool':
                c = ui.Switch(ctl_name,getter=get_ctl,setter=set_ctl)
            elif control['type']=='int':
                c = ui.Slider(ctl_name,getter=get_ctl,min=control['min'],max=control['max'],
                                step=control['step'], setter=set_ctl)

            elif control['type']=="menu":
                if control['menu'] is None:
                    selection = range(control['min'],control['max']+1,control['step'])
                    labels = selection
                else:
                    selection = [value for name,value in control['menu'].iteritems()]
                    labels = [name for name,value in control['menu'].iteritems()]
                c = ui.Selector(ctl_name,getter=get_ctl,selection=selection,labels = labels,setter=set_ctl)
            else:
                pass
            if control['disabled']:
                c.read_only = True
            if ctl_name == 'Exposure, Auto Priority':
                # the controll should always be off. we set it to 0 on init (see above)
                c.read_only = True

            if c is not None:
                self.menu.append(c)

        # self.menu.append(ui.Button("refresh",gui_update_from_device))
        # self.menu.append(ui.Button("load defaults",gui_load_defaults))
        self.menu.collapsed = True
        self.sidebar = sidebar
        #add below geneal settings
        self.sidebar.insert(1,self.menu)

    def deinit_gui(self):
        if self.menu:
            self.sidebar.remove(self.menu)
            self.menu = None



    def close(self):
        self.deinit_gui()
        # self.capture.close()
        del self.capture
        logger.info("Capture released")


def filter_sizes(cam_name,size):
    #here we can force some defaulit formats
    if "6000" in cam_name:
        if size[0] == 640:
            logger.info("HD-6000 camera selected. Forcing format to 640,360")
            return 640,360
        elif size[0] == 320:
            logger.info("HD-6000 camera selected. Forcing format to 320,360")
            return 320,160
    return size

