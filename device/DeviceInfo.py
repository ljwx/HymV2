class DeviceInfo:
    def __init__(self, serial):
        self.serial_no = serial


class Mi15(DeviceInfo):
    def __init__(self):
        super().__init__("192.168.0.107")
        # super().__init__("23a6524e")

class HwP40(DeviceInfo):
    def __init__(self):
        super().__init__("NAB0220416035468")
