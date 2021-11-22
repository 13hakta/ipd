# -*- coding: utf-8 -*-

import time


class Project:
    def __init__(self):
        self.start_count = 0
        self.start = time.time()
        self.last_state = -1
        self.deployment = None
        self.processed = 0

    def process(self, deployment) -> int:
        if self.deployment and self.deployment.state < 4:
            return 1

        self.deployment = deployment
        self.deployment.parent = self

        self.deployment.start()
        self.start_count += 1

        return 0

    def state(self) -> int:
        if self.deployment:
            self.last_state = self.deployment.state

        return self.last_state

    def state_code(self) -> str:
        result = self.state()

        if result < 4:
            return "active"

        if result == 4:
            return "ok"

        return "err"

    def info(self) -> dict:
        result = {
            "start": int(self.start),
            "start_count": self.start_count,
            "processed": self.processed,
        }

        if self.deployment:
            self.last_state = self.deployment.state

            if self.deployment.version:
                result["version"] = self.deployment.version

        result["state"] = self.last_state

        return result
