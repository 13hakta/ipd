# -*- coding: utf-8 -*-

from threading import Thread, Event


class ServiceThread(Thread):
    def __init__(self, manager):
        Thread.__init__(self)

        self.delay = 600
        self.manager = manager

        self.stop_event = Event()
        self.daemon = True

    def run(self) -> None:
        while not self.stop_event.is_set():
            self.manager.cleanup()
            self.stop_event.wait(self.delay)
