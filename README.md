# Pypigpio

A lightweight pigpio-compatible socket server implemented in Python using `libgpiod`.

## Project Layout

- [Pypigpio.py](Pypigpio.py): application entrypoint and config/bootstrap logic
- [Pypigpio.yaml](Pypigpio.yaml): runtime configuration
- [src/gpio_backend.py](src/gpio_backend.py): GPIO backend implementation
- [src/socket_server.py](src/socket_server.py): pigpio socket protocol server
- [pypigpio.service](pypigpio.service): systemd service unit
- [requirements.txt](requirements.txt): Python dependencies

## Requirements

- Linux with GPIO character device support (for example `/dev/gpiochip0`)
- Python 3.10+
- `libgpiod` userspace support

Install Python dependency:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## Configuration

Edit [Pypigpio.yaml](Pypigpio.yaml).

```yaml
app:
  name: pypigpio
  version: "0.01"

gpio:
  CHIP_PATH: /dev/gpiochip0
  CONSUMER: openhab-pigpio-bridge
  HW_REVISION: "0xA02082"

server:
  SERVER_HOST: 0.0.0.0
  SERVER_PORT: 8888

logging:
  LOG_LEVEL: INFO
  LOG_METHOD: PRINT
```

Notes:
- Supported config file formats are `.yaml` and `.yml`.
- Environment variables can override YAML keys (`CHIP_PATH`, `SERVER_PORT`, etc.).

## Run Manually

```bash
source .venv/bin/activate
python3 Pypigpio.py
```

## Run with systemd

Install unit file:

```bash
sudo cp pypigpio.service /etc/systemd/system/pypigpio.service
sudo systemctl daemon-reload
sudo systemctl enable pypigpio
sudo systemctl start pypigpio
```

Service operations:

```bash
sudo systemctl status pypigpio
sudo systemctl restart pypigpio
sudo systemctl stop pypigpio
```

View logs:

```bash
journalctl -u pypigpio -f
```

## Troubleshooting

- `OSError: [Errno 98] Address already in use`
  - Another process is listening on port `8888`.
  - Change `SERVER_PORT` in [Pypigpio.yaml](Pypigpio.yaml) or stop the conflicting service.

- `Config file not found`
  - Ensure [Pypigpio.yaml](Pypigpio.yaml) exists in the project root.

- GPIO permission/access errors
  - Run with sufficient privileges or adjust device permissions/group access for `/dev/gpiochip*`.
