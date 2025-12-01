from device.DeviceConnect import DeviceConnect, DeviceInfo


class DeviceCommonOperation(DeviceConnect):
    def __init__(self, device_info: DeviceInfo):
        self.device = device_info


