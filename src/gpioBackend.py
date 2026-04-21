from __future__ import annotations

import threading
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Callable, Dict

import gpiod
from gpiod.line import Direction, Value

MODE_INPUT = 0
MODE_OUTPUT = 1
DEFAULT_HW_REVISION = 0xA02082


def to_int32(value: int) -> int:
    value &= 0xFFFFFFFF
    if value >= 0x80000000:
        value -= 0x100000000
    return value


class GpioBackend(ABC):
    @abstractmethod
    def close(self) -> None:
        pass

    @abstractmethod
    def get_tick(self) -> int:
        pass

    @abstractmethod
    def get_hw_revision(self) -> int:
        pass

    @abstractmethod
    def set_mode(self, gpio: int, mode: int) -> int:
        pass

    @abstractmethod
    def get_mode(self, gpio: int) -> int:
        pass

    @abstractmethod
    def read(self, gpio: int) -> int:
        pass

    @abstractmethod
    def write(self, gpio: int, level: int) -> int:
        pass

    @abstractmethod
    def read_bank1(self) -> int:
        pass


BackendFactory = Callable[[], GpioBackend]


@dataclass
class LineHandle:
    request: gpiod.LineRequest
    direction: int


class GpiodBackend(GpioBackend):
    """Concrete GPIO backend using libgpiod."""

    def __init__(
        self,
        chip_path: str = "/dev/gpiochip0",
        consumer: str = "openhab-pigpio-bridge",
        hw_revision: int = DEFAULT_HW_REVISION,
        logger: Optional[logging.Logger] = None,
    ) -> None:
    
        self.chip_path = chip_path
        self.consumer = consumer
        self.hw_revision = hw_revision
        self._logger = logger or logging.getLogger("Pypigpio.GpiodBackend")

        self._chip = gpiod.Chip(chip_path)
        self._lock = threading.RLock()
        self._lines: Dict[int, LineHandle] = {}
        self._start_time = time.monotonic()

    def close(self) -> None:
        with self._lock:
            for handle in self._lines.values():
                try:
                    handle.request.release()
                except Exception:
                    pass
            self._lines.clear()
            try:
                self._chip.close()
            except Exception:
                pass

    def get_tick(self) -> int:
        micros = int((time.monotonic() - self._start_time) * 1_000_000)
        return to_int32(micros)

    def get_hw_revision(self) -> int:
        return to_int32(self.hw_revision)

    def _ensure_valid_gpio(self, gpio: int) -> None:
        if gpio < 0 or gpio > 53:
            raise ValueError(f"invalid GPIO {gpio}")

    def _request_line(self, gpio: int, direction: int) -> gpiod.LineRequest:
        settings = gpiod.LineSettings(
            direction=Direction.OUTPUT if direction == MODE_OUTPUT else Direction.INPUT
        )
        return self._chip.request_lines(
            consumer=self.consumer,
            config={gpio: settings},
        )

    def _get_or_request_line(self, gpio: int, direction: int) -> gpiod.LineRequest:
        self._ensure_valid_gpio(gpio)

        existing = self._lines.get(gpio)
        if existing is not None and existing.direction == direction:
            return existing.request

        if existing is not None:
            existing.request.release()
            del self._lines[gpio]

        request = self._request_line(gpio, direction)
        self._lines[gpio] = LineHandle(request=request, direction=direction)
        return request

    def set_mode(self, gpio: int, mode: int) -> int:
        if mode not in (MODE_INPUT, MODE_OUTPUT):
            raise ValueError(f"invalid mode {mode}")

        with self._lock:
            self._get_or_request_line(gpio, mode)
        return 0

    def get_mode(self, gpio: int) -> int:
        self._ensure_valid_gpio(gpio)

        with self._lock:
            existing = self._lines.get(gpio)
            if existing is None:
                return MODE_INPUT
            return existing.direction

    def read(self, gpio: int) -> int:
        with self._lock:
            request = self._get_or_request_line(gpio, MODE_INPUT)
            value = request.get_value(gpio)
            self._logger.info("Read GPIO %d: %d", gpio, value)
            return 1 if value == Value.ACTIVE else 0

    def write(self, gpio: int, level: int) -> int:
        if level not in (0, 1):
            raise ValueError(f"invalid level {level}")

        with self._lock:
            request = self._get_or_request_line(gpio, MODE_OUTPUT)
            request.set_value(gpio, Value.ACTIVE if level else Value.INACTIVE)
            self._logger.info("Wrote GPIO %d: %d", gpio, level)
        return 0

    def read_bank1(self) -> int:
        with self._lock:
            mask = 0
            for gpio in range(32):
                try:
                    request = self._get_or_request_line(gpio, MODE_INPUT)
                    value = request.get_value(gpio)
                    if value == Value.ACTIVE:
                        mask |= (1 << gpio)
                except Exception:
                    pass
            return to_int32(mask)
