class DeviceInfo:
    def __init__(self, serial):
        self.serial_no = serial


class Mi15(DeviceInfo):
    def __init__(self):
        super().__init__("24129PN74C")

class HwP40(DeviceInfo):
    def __init__(self):
        super().__init__("NAB0220416035468")
