from abc import ABC, abstractmethod


class AppRunProtocol(ABC):

    @abstractmethod
    def launch_app(self) -> bool: ...

    @abstractmethod
    def common_step(self) -> bool: ...

    @abstractmethod
    def handle_dialog(self): ...

    @abstractmethod
    def is_home_page(self) -> bool: ...

    @abstractmethod
    def go_task_page(self) -> bool: ...

    @abstractmethod
    def check_in(self) -> bool: ...

    @abstractmethod
    def get_balance(self) -> str: ...

    @abstractmethod
    def loop_task(self): ...
