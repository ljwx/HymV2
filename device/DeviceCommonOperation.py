from device.DeviceConnect import DeviceConnect, DeviceInfo


class DeviceCommonOperation(DeviceConnect):
    def __init__(self, device_info: DeviceInfo):
        super().__init__(device_info)

    def swipe_up(self, start_y_ratio=0.8, end_y_ratio=0.2):
        screen_size = self.get_screen_size()
        width, height = screen_size

        start_x = width // 2
        start_y = int(height * start_y_ratio)
        end_x = width // 2
        end_y = int(height * end_y_ratio)

        self.dev.swipe((start_x, start_y), (end_x, end_y))

    def swipe_down(self, start_y_ratio=0.2, end_y_ratio=0.8):
        screen_size = self.get_screen_size()
        width, height = screen_size

        start_x = width // 2
        start_y = int(height * start_y_ratio)
        end_x = width // 2
        end_y = int(height * end_y_ratio)

        self.dev.swipe((start_x, start_y), (end_x, end_y))
