from device.DeviceUserOperation import DeviceCommonOperation
from device.DeviceBase import DeviceInfo


class DeviceManager(DeviceCommonOperation):
    def __init__(self, device_info: DeviceInfo):
        super().__init__(device_info)

    def init_status(self):
        pass