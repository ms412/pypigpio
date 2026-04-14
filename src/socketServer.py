
import socket
import struct
import threading
import time


# PIGPIO Konstanten
PI_CMD_MODES = 0    # Set Mode
PI_CMD_MODEG = 1    # Get Mode
PI_CMD_READ  = 3    # Read
PI_CMD_WRITE = 4    # Write
PI_CMD_BR1   = 10   # Bank 1 Read
PI_CMD_TICK  = 16   # Get Tick
PI_CMD_HWVER = 17   # HW Version
PI_CMD_VER   = 26   # PIGPIO Version
PI_CMD_NOIB  = 99   # Handshake

VERSION = 79
START_TIME = time.monotonic()


class socketServer:
    def __init__(self, host, port):
        self.host = host
        self.port = port
    

    def handle_client(conn, addr, chip):
        print(f"[+] Client verbunden: {addr}")
        try:
            while True:
                data = conn.recv(16)
                if not data or len(data) < 16:
                    break

                cmd, p1, p2, p3 = struct.unpack("IIII", data)

                # LOGGING: Eingehend
                print(f"  --> RECV: CMD={cmd:2} | p1={p1:<10} | p2={p2:<10} | p3={p3:<10}")

                result = 0

                try:
                    if cmd == PI_CMD_NOIB:
                        print(">>> handshake from client")
                        result = 0

                    elif cmd == PI_CMD_VER:
                        print(">>> version request from client")
                        result = VERSION

                    elif cmd == PI_CMD_TICK:
                        result = get_tick()
                        print(">>> tick request from client",result)

                    elif cmd == PI_CMD_HWVER:
                        print(">>> hardware version request from client")
                        result = 0xA02082 # Pi Revision
                        result = get_rpi_revision() or 0xA02082
                    #  print(hex(result))
                        print(f"Raspberry Pi Revision: {hex(result)}")
                        revision = result 

                    # MODES: p1=gpio, p2=mode (0:IN, 1:OUT)
                    elif cmd == PI_CMD_MODES:
                        print(f">>> set mode request: GPIO {p1} -> {'OUTPUT' if p2 == 1 else 'INPUT'}")
                        get_gpio_line(chip, p1, mode=p2)
                        result = 0

                    # WRITE: p1=gpio, p2=level (0:Low, 1:High)
                    elif cmd == PI_CMD_WRITE:
                        print(f">>> write request: GPIO {p1} -> {'HIGH' if p2 == 1 else 'LOW'}")
                        line = get_gpio_line(chip, p1)
                        val = Value.ACTIVE if p2 else Value.INACTIVE
                        line.set_value(p1, val)
                        result = 0

                    # READ: p1=gpio
                    elif cmd == PI_CMD_READ:
                        print(f">>> read request: GPIO {p1}")   
                        line = get_gpio_line(chip, p1)
                        val = line.get_value(p1)
                        result = 1 if val == Value.ACTIVE else 0

                    # BANK READ 1 (GPIO 0-31)
                    elif cmd == PI_CMD_BR1:
                        print(">>> bank read 1 request from client")
                        bank = 0
                        with lock:
                            for offset, req in active_lines.items():
                                if 0 <= offset < 32:
                                    if req.get_value(offset) == Value.ACTIVE:
                                        bank |= (1 << offset)
                        result = bank

                except Exception as e:
                    print(f"[!] GPIO Fehler bei Pin {p1}: {e}")
                    result = -1

                # PIGPIO Response: cmd, p1, p2, result (jeweils 4 Bytes)
                response = struct.pack("IIII", cmd, p1, p2, result & 0xFFFFFFFF)

                # LOGGING: Ausgehend
                print(f"  <-- SEND: CMD={cmd:2} | p1={p1:<10} | p2={p2:<10} | res={result:<10}")

                try:
                    conn.sendall(response)
                except Exception as e:
                    print(f"[!] Fehler beim Senden der Antwort an {addr}: {e}"  )

        finally:
            conn.close()
            print(f"[-] Client getrennt: {addr}")

    def start_server():
        print(f"PIGPIO-gpiod Bridge läuft auf {self.host}:{self.port}")

        print(f"Raspberry Pi Revision: {hex(get_rpi_revision())}")

        
        # Chip einmalig beim Start öffnen
        with gpiod.Chip(CHIP_PATH) as chip:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            s.bind((self.host, self.port))
            s.listen()

            while True:
                conn, addr = s.accept()
                threading.Thread(
                    target=handle_client,
                    args=(conn, addr, chip),
                    daemon=True
                ).start()
