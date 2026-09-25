# -*- coding: utf-8 -*-

import os
import os.path
import subprocess
import shutil
import tarfile
import uuid
import logging
from threading import Thread
from typing import TYPE_CHECKING, Optional

from werkzeug.utils import secure_filename

if TYPE_CHECKING:
    from .manager import ProjectManager
    from .project import Project


# -1  - Wait in queue
# 0   - Start process
# 101 - No package file
# 102 - No folder
# 103 - Cant unpack
# 104 - Cant prepare
# 105 - Cant deploy
# 106 - Control script missing or not executable
# 103x - Timeout execution

TIMEOUT = 1800


def env_timeout(name: str) -> int:
    """Per-step subprocess timeout from environment, TIMEOUT by default"""
    try:
        return max(1, int(os.environ.get(name, TIMEOUT)))
    except ValueError:
        logging.warning("Invalid %s value, using default %d", name, TIMEOUT)
        return TIMEOUT


class Deployment:
    def __init__(
        self,
        project: str,
        upload_dir: str,
        image_filename: str,
        version: Optional[str] = None,
    ):
        self.state = 0
        self.uuid = str(uuid.uuid4())
        self.idempotency_key = None
        self.thread: Optional[Thread] = None
        self.parent: Optional["Project"] = None
        self.manager: Optional["ProjectManager"] = None

        self.project = project
        self.version = version
        self.upload_folder = os.path.join(upload_dir, f"{project}-{self.uuid}")
        self.package_file = os.path.join(upload_dir, f"package.tar.{self.uuid}")
        self.image_file = os.path.join(
            self.upload_folder, secure_filename(image_filename)
        )
        self.control_script = os.path.join(self.upload_folder, "control.sh")

    def __str__(self):
        return f"{self.project}: {self.uuid}"

    def save(self, package, image) -> None:
        """Store uploaded files on disk"""
        os.mkdir(self.upload_folder)
        package.save(self.package_file)
        image.save(self.image_file)

    def discard(self) -> None:
        """Remove uploaded files after failed deployment setup"""
        try:
            os.unlink(self.package_file)
        except FileNotFoundError:
            pass

        shutil.rmtree(self.upload_folder, ignore_errors=True)

    def cleanup(self, code: int) -> int:
        try:
            os.unlink(self.package_file)
        except FileNotFoundError:
            pass

        shutil.rmtree(self.upload_folder, ignore_errors=True)

        if self.parent is None or self.manager is None:
            # Deployed outside of the manager (e.g. in tests)
            self.state = code
            return self.state

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

    def log_step_error(self, step: str, cpe: subprocess.CalledProcessError) -> None:
        """Log stderr of a failed control script command (from dev branch)"""
        if cpe.stderr:
            logging.error(
                "[%s:%s] %s error output: %s",
                self.project,
                self.uuid,
                step,
                cpe.stderr.strip(),
            )

    def process(self) -> int:
        logging.info("[%s:%s] Start deploy", self.project, self.uuid)
        self.state = 1

        env = {"PATH": os.environ["PATH"], "PROJECT": self.project, "DEPLOY": self.uuid}

        check_timeout = env_timeout("CHECK_TIMEOUT")
        prepare_timeout = env_timeout("PREPARE_TIMEOUT")
        deploy_timeout = env_timeout("DEPLOY_TIMEOUT")

        # UNPACK

        try:
            with tarfile.open(self.package_file) as tf:
                tf.extractall(self.upload_folder, filter="data")
        except (tarfile.TarError, OSError) as exc:
            logging.error("[%s] Cant unpack: %s", self.project, exc)
            return self.cleanup(103)

        self.state = 2

        # CHECK environment

        return_code = 0

        try:
            subprocess.run(
                [self.control_script, "check"],
                cwd=self.upload_folder,
                env=env,
                timeout=check_timeout,
                check=True,
                capture_output=True,
                text=True,
            )
        except subprocess.TimeoutExpired:
            logging.error("[%s] Cant check, timeout", self.project)
            return self.cleanup(1031)
        except OSError as exc:
            logging.error("[%s] Cant run control script: %s", self.project, exc)
            return self.cleanup(106)
        except subprocess.CalledProcessError as cpe:
            return_code = cpe.returncode
            self.log_step_error("Check", cpe)

        # Need to prepare environment
        if return_code != 1:
            try:
                subprocess.run(
                    [self.control_script, "prepare"],
                    cwd=self.upload_folder,
                    env=env,
                    timeout=prepare_timeout,
                    check=True,
                    capture_output=True,
                    text=True,
                )
            except subprocess.TimeoutExpired:
                logging.error("[%s] Cant prepare, timeout", self.project)
                return self.cleanup(1032)
            except OSError as exc:
                logging.error(
                    "[%s] Cant prepare, control script not runnable: %s",
                    self.project,
                    exc,
                )
                self.state = 104
                return self.cleanup(self.state)
            except subprocess.CalledProcessError as cpe:
                self.log_step_error("Prepare", cpe)
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
                cwd=self.upload_folder,
                env=env,
                timeout=deploy_timeout,
                check=True,
                capture_output=True,
                text=True,
            )
        except subprocess.TimeoutExpired:
            logging.error("[%s] Cant deploy, timeout", self.project)
            return self.cleanup(1033)
        except OSError as exc:
            logging.error("[%s] Cant run control script: %s", self.project, exc)
            return self.cleanup(106)
        except subprocess.CalledProcessError as cpe:
            return_code = cpe.returncode
            self.log_step_error("Deploy", cpe)

        if return_code != 1:
            logging.error(
                "[%s:%s] Cant deploy, returned %d",
                self.project,
                self.uuid,
                return_code,
            )
            return self.cleanup(105)

        try:
            if self.parent is not None:
                self.parent.processed += os.path.getsize(self.image_file)
        except OSError:
            pass

        logging.info("[%s:%s] Deploy successful", self.project, self.uuid)
        return self.cleanup(4)
