# -*- coding: utf-8 -*-

import time


class Project:
    def __init__(self):
        self.start_count = 0
        self.start = time.time()
        self.last_state = -1
        self.deployment = None
        self.processed = 0

    def process(self, deployment):
        if self.deployment and self.deployment.state < 4:
            return 1

        self.deployment = deployment
        self.deployment.parent = self

        self.deployment.start()
        self.start_count += 1

        return 0

    def state(self):
        if self.deployment:
            self.last_state = self.deployment.state

        return self.last_state

    def state_code(self):
        result = self.state()

        if result < 4:
            return "active"

        if result == 4:
            return "ok"

        return "err"

    def info(self):
        if self.deployment:
            self.last_state = self.deployment.state

        return {
            "start": int(self.start),
            "state": self.last_state,
            "start_count": self.start_count,
            "processed": self.processed,
        }
