# -*- coding: utf-8 -*-

import os
import os.path
import subprocess
import shutil
import uuid
import logging
from threading import Thread

# -1  - Wait in queue
# 0   - Start process
# 101 - No package file
# 102 - No folder
# 103 - Cant unpack
# 104 - Cant prepare
# 105 - Cant deploy
# 103* - Timeout execution

TIMEOUT = 1800


class Deployment:
    def __init__(
        self,
        project: str,
        upload_folder: str,
        package_file: str,
        image_file: str,
        version: str = None,
    ):
        self.state = 0
        self.uuid = str(uuid.uuid4())
        self.thread = None
        self.parent = None
        self.manager = None

        self.upload_folder = upload_folder.replace("..", "")

        self.project = project
        self.version = version
        self.package_file = package_file
        self.image_file = image_file
        self.control_script = self.upload_folder + "/control.sh"

    def __str__(self):
        return f"{self.project}: {self.uuid}"

    def cleanup(self, code: str) -> int:
        os.unlink(self.package_file)
        shutil.rmtree(self.upload_folder)
        self.parent.deployment = None
        self.parent.last_state = code
        self.state = code
        self.manager.next()
        return self.state

    def check(self) -> int:
        if self.state:
            return self.state

        if not os.path.exists(self.package_file):
            self.state = 101
            return self.state

        if not os.path.exists(self.upload_folder):
            self.state = 102
            return self.state

        self.state = 0
        return self.state

    def start(self) -> None:
        self.thread = Thread(target=self.process)
        self.thread.start()

    def process(self) -> int:
        logging.info("[%s:%s] Start deploy", self.project, self.uuid)
        self.state = 1

        env = {"PATH": os.environ["PATH"], "PROJECT": self.project, "DEPLOY": self.uuid}

        # UNPACK

        try:
            subprocess.run(
                ["tar", "xf", self.package_file, "-C", self.upload_folder],
                env=env,
                timeout=TIMEOUT,
                check=True,
                capture_output=True,
            )
        except subprocess.TimeoutExpired as te:
            logging.error("[%s] Cant unpack, timeout", self.project)
            return self.cleanup(1030)
        except subprocess.CalledProcessError as cpe:
            if cpe.stderr:
                logging.error(
                    "[%s:%s] Unpack error output: %s",
                    self.project,
                    self.uuid,
                    cpe.stderr,
                )

            logging.error("[%s] Cant unpack, retcode=%d", self.project, cpe.returncode)
            return self.cleanup(103)

        os.chdir(self.upload_folder)

        self.state = 2

        # CHECK environment

        return_code = 0

        try:
            subprocess.run(
                [self.control_script, "check"],
                env=env,
                timeout=TIMEOUT,
                check=True,
                capture_output=True,
            )
        except subprocess.TimeoutExpired as te:
            logging.error("[%s] Cant check, timeout", self.project)
            return self.cleanup(1031)
        except subprocess.CalledProcessError as cpe:
            return_code = cpe.returncode

            if cpe.stderr:
                logging.error(
                    "[%s:%s] Check error output: %s",
                    self.project,
                    self.uuid,
                    cpe.stderr,
                )

        # Need to prepare environment
        if return_code != 1:
            try:
                subprocess.run(
                    [self.control_script, "prepare"],
                    env=env,
                    timeout=TIMEOUT,
                    check=True,
                    capture_output=True,
                )
            except subprocess.TimeoutExpired as te:
                logging.error("[%s] Cant prepare, timeout", self.project)
                return self.cleanup(1032)
            except subprocess.CalledProcessError as cpe:
                if cpe.stderr:
                    logging.error(
                        "[%s:%s] Prepare error output: %s",
                        self.project,
                        self.uuid,
                        cpe.stderr,
                    )

                logging.error(
                    "[%s] Cant prepare environment, retcode=%d",
                    self.project,
                    cpe.returncode,
                )
                self.state = 104
                return self.cleanup(self.state)

        self.state = 3

        # DEPLOY

        return_code = 0

        try:
            subprocess.run(
                [self.control_script, "deploy"],
                env=env,
                timeout=TIMEOUT,
                check=True,
                capture_output=True,
            )
        except subprocess.TimeoutExpired as te:
            logging.error("[%s] Cant deploy, timeout", self.project)
            return self.cleanup(1033)
        except subprocess.CalledProcessError as cpe:
            return_code = cpe.returncode

            if cpe.stderr:
                logging.error(
                    "[%s:%s] Deploy error output: %s",
                    self.project,
                    self.uuid,
                    cpe.stderr,
                )

        if return_code != 1:
            logging.error(
                "[%s:%s] Cant deploy, returned %d", self.project, self.uuid, return_code
            )
            return self.cleanup(105)

        self.parent.processed += os.path.getsize(self.image_file)

        logging.info("[%s:%s] Deploy successful", self.project, self.uuid)
        return self.cleanup(4)
