from device.DeviceBase import DeviceBase
from device.DeviceInfo import DeviceInfo


class DeviceCommon(DeviceBase):
    def __init__(self, device_info: DeviceInfo):
        super().__init__(device_info)
