# -*- coding: utf-8 -*-

"""Minimal systemd sd_notify support on pure stdlib."""

import logging
import os
import socket
from threading import Event, Thread


def sd_notify(message: str) -> None:
    """Send a notification to systemd, silently skip when not under systemd"""
    address = os.environ.get("NOTIFY_SOCKET")

    if not address:
        return

    if address.startswith("@"):
        address = "\0" + address[1:]

    try:
        with socket.socket(socket.AF_UNIX, socket.SOCK_DGRAM) as sock:
            sock.connect(address)
            sock.sendall(message.encode())
    except OSError as exc:
        logging.warning("sd_notify failed: %s", exc)


class WatchdogThread(Thread):
    """Ping systemd watchdog every WATCHDOG_USEC / 2"""

    def __init__(self):
        Thread.__init__(self)
        self.daemon = True
        self.stop_event = Event()

        try:
            usec = int(os.environ.get("WATCHDOG_USEC", "0"))
        except ValueError:
            usec = 0

        self.interval = usec / 2 / 1_000_000 if usec > 0 else 0

    def run(self) -> None:
        if self.interval <= 0:
            return

        while not self.stop_event.wait(self.interval):
            sd_notify("WATCHDOG=1")
