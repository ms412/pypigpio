#!/usr/bin/env python3
from __future__ import annotations

__app__ = "pypigpio"
__DATE__ = "21.04.2026"
__author__ = "Markus Schiesser"
__contact__ = "M.Schiesser@gmail.com"
__copyright__ = "Copyright (C) 2026 Markus Schiesser"
__license__ = "Beerware License Version 42"



import logging
import os  
from pathlib import Path
from logging.handlers import SysLogHandler

from typing import Dict, Optional

from src.gpioBackend import DEFAULT_HW_REVISION, GpiodBackend
from src.socketServer import SocketServer

class Pypigpio(object):
    def __init__(self, config="pypigpio.yaml"):
        self._config = config
        self._logger = logging.getLogger("Pypigpio")

    def __del__(self):
        self.stop_server()  

    def _parse_simple_yaml_config(self, file_path: Path) -> Dict[str, str]:
        values: Dict[str, str] = {}
        current_section: Optional[str] = None

        with file_path.open("r", encoding="utf-8") as cfg_file:
            for raw_line in cfg_file:
                line = raw_line.rstrip("\n")
                stripped = line.strip()

                if not stripped or stripped.startswith("#"):
                    continue

                if ":" not in stripped:
                    continue

                # Section header like "gpio:".
                if stripped.endswith(":") and stripped.count(":") == 1:
                    current_section = stripped[:-1].strip().lower()
                    continue

                key, value = stripped.split(":", 1)
                key = key.strip()
                value = value.strip().strip('"').strip("'")

                if not key:
                    continue

                # For this config schema, only use known sections.
                if line[:1].isspace() and current_section in ("gpio", "server", "logging"):
                    values[key] = value
                elif not line[:1].isspace():
                    values[key] = value

        return values

    def read_config(self):
        env_path = Path(__file__).parent / self._config 
        if not env_path.is_file():
            self._logger.error("Config file not found: %s", env_path)
            raise FileNotFoundError(f"Config file not found: {env_path}")       
            return False

        config_values: Dict[str, object] = {}
        suffix = env_path.suffix.lower()

        if suffix not in (".yaml", ".yml"):
            raise ValueError(f"Unsupported config format: {env_path}. Use .yaml or .yml")

        config_values = self._parse_simple_yaml_config(env_path)
        
        self._chip_path = os.getenv("CHIP_PATH", str(config_values.get("CHIP_PATH", "/dev/gpiochip0")))
        self._consumer = os.getenv("CONSUMER", str(config_values.get("CONSUMER", "openhab-pigpio-bridge")))
        self._hw_revision = int(os.getenv("HW_REVISION", str(config_values.get("HW_REVISION", hex(DEFAULT_HW_REVISION)))), 16)

        self._server_host = os.getenv("SERVER_HOST", str(config_values.get("SERVER_HOST", "0.0.0.0")))
        self._server_port = int(os.getenv("SERVER_PORT", str(config_values.get("SERVER_PORT", "8888"))))
        self._version = os.getenv("VERSION", str(config_values.get("version", "0.02")))

        self._logger.info(
            "Configuration loaded: CHIP_PATH=%s CONSUMER=%s HW_REVISION=%s SERVER_HOST=%s SERVER_PORT=%d",
            self._chip_path,
            self._consumer,
            hex(self._hw_revision),
            self._server_host,
            self._server_port,
        )


        self._log_level = os.getenv("LOG_LEVEL", str(config_values.get("LOG_LEVEL", "INFO"))).upper()
        if self._log_level not in ("DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"):
            self._logger.warning("Invalid LOG_LEVEL: %s, defaulting to INFO", self._log_level)
            self._log_level = "INFO"
        
        self._log_method = os.getenv("LOG_METHOD", str(config_values.get("LOG_METHOD", "PRINT"))).upper()
        if self._log_method not in ("PRINT", "FILE","SYSLOG"):
            self._logger.warning("Invalid LOG_METHOD: %s, defaulting to PRINT", self._log_method)
            self._log_method = "PRINT"  

        return True

    def start_loggin(self):
        if self._log_method == "FILE":
            logging.basicConfig(filename='pypigpio.log', level=self._log_level, format='%(asctime)s - %(levelname)s - %(message)s')         
        elif self._log_method == "SYSLOG":
            logging.basicConfig(level=self._log_level, format='%(asctime)s - %(levelname)s - %(message)s', handlers=[SysLogHandler(address='/dev/log')])
        else:
            logging.basicConfig(level=self._log_level, format='%(asctime)s - %(levelname)s - %(message)s')  

        self._logger = logging.getLogger("Pypigpio")

        return True

    def start_gpio(self):
        self._gpio = GpiodBackend(chip_path=self._chip_path, consumer=self._consumer, hw_revision=self._hw_revision)
        return True

    def start_server(self):
        self._server = SocketServer(
            gpio_factory=lambda: self._gpio,
            host=self._server_host,
            port=self._server_port,
            logger=self._logger,
        )
        self._server.start()
        return True

    def stop_server(self):
        self._logger.info("Shutting down server...")
        self._server.stop()
        self._gpio.close()


    def start(self):
        self.read_config()
        self.start_loggin()
        self._logger.info("Starting Pypigpio server...{version} (HW Rev: {hw_rev})".format(version=self._version, hw_rev=hex(self._hw_revision)))

        self.start_gpio()
        self.start_server() 

if __name__ == "__main__":
    pypigpio = Pypigpio()
    try:
        pypigpio.start()
    except Exception:
        logging.getLogger("Pypigpio").exception("Server startup failed")
        raise