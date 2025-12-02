from device.DeviceCommonOperation import DeviceCommonOperation
from device.DeviceConnect import DeviceInfo


class DeviceManager(DeviceCommonOperation):
    def __init__(self, device_info: DeviceInfo):
        super().__init__(device_info)