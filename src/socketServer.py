from __future__ import annotations

import logging
import socket
import struct
import threading
from typing import Optional, Tuple

from src.gpioBackend import BackendFactory, GpioBackend, to_int32

PI_CMD_MODES = 0
PI_CMD_MODEG = 1
PI_CMD_READ = 3
PI_CMD_WRITE = 4
PI_CMD_BR1 = 10
PI_CMD_TICK = 16
PI_CMD_HWVER = 17
PI_CMD_NOOP = 18
PI_CMD_VER = 26
PI_CMD_NOIB = 99

PIGPIO_VERSION = 79


def recv_all(conn: socket.socket, size: int) -> Optional[bytes]:
    data = b""
    while len(data) < size:
        chunk = conn.recv(size - len(data))
        if not chunk:
            return None
        data += chunk
    return data


class SocketServer:
    """Socket/protocol layer only."""

    def __init__(
        self,
        gpio_factory: BackendFactory,
        host: str = "0.0.0.0",
        port: int = 8888,
        logger: Optional[logging.Logger] = None,
    ) -> None:
    
        self.host = host
        self.port = port
        self._gpio_factory = gpio_factory
        self._gpio: GpioBackend = gpio_factory()
        self._logger = logger or logging.getLogger("Pypigpio.Server")

        self._server_socket: Optional[socket.socket] = None
        self._running = False

    def start(self) -> None:
        self._running = True

        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as server:
            self._server_socket = server
            server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            server.bind((self.host, self.port))
            server.listen()

            self._logger.info("pigpio server listening on %s:%d", self.host, self.port)

            while self._running:
                try:
                    conn, addr = server.accept()
                except OSError:
                    break

                thread = threading.Thread(
                    target=self._handle_client,
                    args=(conn, addr),
                    daemon=True,
                )
                thread.start()

    def stop(self) -> None:
        self._running = False

        if self._server_socket is not None:
            try:
                self._server_socket.close()
            except Exception:
                pass

        self._gpio.close()

    def _dispatch(self, cmd: int, p1: int, p2: int, p3: int) -> int:
        self._logger.debug("dispatching cmd=%d p1=%d p2=%d p3=%d", cmd, p1, p2, p3)

        if cmd == PI_CMD_NOIB:
            return 0

        if cmd == PI_CMD_NOOP:
            return 0

        if cmd == PI_CMD_VER:
            return PIGPIO_VERSION

        if cmd == PI_CMD_HWVER:
            return self._gpio.get_hw_revision()

        if cmd == PI_CMD_TICK:
            return self._gpio.get_tick()

        if cmd == PI_CMD_MODES:
            return self._gpio.set_mode(p1, p2)

        if cmd == PI_CMD_MODEG:
            return self._gpio.get_mode(p1)

        if cmd == PI_CMD_READ:
            return self._gpio.read(p1)

        if cmd == PI_CMD_WRITE:
            return self._gpio.write(p1, p2)

        if cmd == PI_CMD_BR1:
            return self._gpio.read_bank1()

        return -1

    def _handle_client(self, conn: socket.socket, addr: Tuple[str, int]) -> None:
        self._logger.info("client connected: %s", addr)

        try:
            while True:
                data = recv_all(conn, 16)
                if data is None:
                    break

                cmd, p1, p2, p3 = struct.unpack("<iiii", data)

                try:
                    res = self._dispatch(cmd, p1, p2, p3)
                except ValueError as exc:
                    self._logger.warning("invalid request from %s: %s", addr, exc)
                    res = -2
                except Exception as exc:
                    self._logger.exception("backend error from %s: %s", addr, exc)
                    res = -3

                self._logger.debug("RESP cmd=%3d p1=%3d p2=%3d p3=%11d -> RES %d", cmd, p1, p2, p3, res)

                response = struct.pack(
                    "<iiii",
                    to_int32(cmd),
                    to_int32(p1),
                    to_int32(p2),
                    to_int32(res),
                )
                conn.sendall(response)

                self._logger.debug(
                    "REQ cmd=%3d p1=%3d p2=%3d p3=%11d -> RES %d",
                    cmd,
                    p1,
                    p2,
                    p3,
                    res,
                )

        except ConnectionResetError:
            pass
        except OSError as exc:
            self._logger.warning("socket error with %s: %s", addr, exc)
        finally:
            try:
                conn.close()
            except Exception:
                pass
            self._logger.info("client disconnected: %s", addr)