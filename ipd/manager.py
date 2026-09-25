# -*- coding: utf-8 -*-

from threading import RLock
import logging
import os
import re
import shutil
import time
import uuid as uuid_module
from typing import Optional

from .project import Project

# Leftover files of a deployment interrupted by a service restart:
# upload dir entry "{project}-{uuid}" or package "package.tar.{uuid}"
PACKAGE_RE = re.compile(r"^package\.tar\.(.+)$")
UUID_RE = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$",
    re.IGNORECASE,
)

TTL = 86400
QUEUE_MAX = 200
TASKS_MAX = 5


def _is_uuid(value: str) -> bool:
    try:
        uuid_module.UUID(value)
        return True
    except (ValueError, AttributeError):
        return False


class ProjectManager:
    def __init__(self):
        self.deployment_queue = []
        self.projects = {}
        self._lock = RLock()
        self._uploads = 0
        self.start = time.time()

    def _process(self, deployment) -> int:
        """Register deployment in its project and start it.

        Returns 0 when processing started, 1 when the project is
        already running another deployment.
        """
        deployment.manager = self

        if deployment.project not in self.projects:
            self.projects[deployment.project] = Project()

        return self.projects[deployment.project].process(deployment)

    def _running_count(self) -> int:
        result = 0

        for project in self.projects.values():
            if 0 < project.state() < 4:
                result += 1

        return result

    def next(self) -> None:
        """Start queued deployments while capacity allows.

        The queue is served LIFO by design: a newer upload is a newer
        version and is more important than older ones. Deployments of
        busy projects stay in the queue and are not lost.
        """
        with self._lock:
            idx = len(self.deployment_queue) - 1

            while idx >= 0 and self._running_count() < TASKS_MAX:
                deployment = self.deployment_queue[idx]

                if self._process(deployment) == 0:
                    del self.deployment_queue[idx]
                # else: project is busy, deployment remains queued

                idx -= 1

    def add(self, deployment) -> int:
        with self._lock:
            if len(self.deployment_queue) >= QUEUE_MAX:
                return 1

            if deployment.project not in self.projects:
                self.projects[deployment.project] = Project()

            project = self.projects[deployment.project]

            replaced = None

            # A newer upload of the same project supersedes the older
            # awaiting deployment.
            for idx, item in enumerate(self.deployment_queue):
                if item.project == deployment.project:
                    replaced = item
                    self.deployment_queue[idx] = deployment
                    break
            else:
                self.deployment_queue.append(deployment)

            if replaced is not None:
                project.mark_superseded(replaced.uuid)

            self._uploads += 1

        if replaced is not None:
            logging.info(
                "[%s] Deployment %s superseded by %s",
                deployment.project,
                replaced.uuid,
                deployment.uuid,
            )
            replaced.discard()

        self.next()

        return 0

    def get(self, project: str) -> Project:
        with self._lock:
            return self.projects.get(project)

    def get_state(self, project: str, deployment_uuid: Optional[str] = None) -> str:
        with self._lock:
            for item in self.deployment_queue:
                if item.uuid == deployment_uuid:
                    return "await"

                if not deployment_uuid and item.project == project:
                    return "await"

            project_obj = self.projects.get(project)

            if not project_obj:
                return "no"

            if deployment_uuid:
                if deployment_uuid in project_obj.superseded:
                    return "changed"

                if (
                    project_obj.deployment
                    and project_obj.deployment.uuid != deployment_uuid
                ):
                    return "changed"

            return project_obj.state_code()

    def list(self) -> str:
        with self._lock:
            return "\n".join(self.projects)

    def stat(self) -> dict:
        with self._lock:
            return {
                "projects": len(self.projects),
                "queue": len(self.deployment_queue),
                "uploads": self._uploads,
            }

    def recover(self, upload_dir: str) -> int:
        """Remove leftovers of deployments interrupted by a restart.

        The queue lives in memory, so after a restart nothing references
        on-disk upload files anymore. Only entries named by the service
        itself ("{project}-{uuid}" dirs and "package.tar.{uuid}" files)
        are removed, anything else in the directory is left untouched.
        """
        cleaned = 0

        try:
            entries = os.listdir(upload_dir)
        except OSError as exc:
            logging.warning("Recover: cant list %s: %s", upload_dir, exc)
            return 0

        for name in entries:
            path = os.path.join(upload_dir, name)
            match = PACKAGE_RE.match(name)

            if match:
                leftover = _is_uuid(match.group(1))
            elif os.path.isdir(path):
                # Deployment upload folders end with "-{uuid}";
                # the uuid itself contains hyphens, take its full length
                leftover = len(name) > 37 and name[-37] == "-" and _is_uuid(name[-36:])
            else:
                leftover = False

            if not leftover:
                continue

            logging.info("Recover: remove leftover %s", name)

            if os.path.isdir(path):
                shutil.rmtree(path, ignore_errors=True)
            else:
                try:
                    os.unlink(path)
                except OSError:
                    pass

            cleaned += 1

        if cleaned:
            logging.info(
                "Recover: cleaned %d leftover items in %s", cleaned, upload_dir
            )

        return cleaned

    def stop(self, timeout: float = 60.0) -> None:
        """Wait for running deployments to finish (graceful shutdown)"""
        deadline = time.time() + timeout

        with self._lock:
            running = [
                project.deployment
                for project in self.projects.values()
                if project.deployment and project.deployment.thread
            ]

        if running:
            logging.info("Shutdown: waiting for %d running deployment(s)", len(running))

        for deployment in running:
            remaining = max(0.0, deadline - time.time())

            if deployment.thread:
                deployment.thread.join(remaining)

        for deployment in running:
            if deployment.thread and deployment.thread.is_alive():
                logging.warning(
                    "Shutdown: deployment %s still running after timeout", deployment
                )

    def find_idempotent(self, project: str, key: str):
        """Find a queued or running deployment by idempotency key"""
        with self._lock:
            for item in self.deployment_queue:
                if item.project == project and item.idempotency_key == key:
                    return item

            project_obj: Optional[Project] = self.projects.get(project)

            if project_obj and project_obj.deployment:
                deployment = project_obj.deployment

                if deployment.idempotency_key == key and deployment.state < 4:
                    return deployment

        return None

    def metrics(self) -> str:
        """Service statistics in Prometheus text format"""
        with self._lock:
            processed = sum(project.processed for project in self.projects.values())
            lines = [
                "# HELP ipd_projects Number of known projects.",
                "# TYPE ipd_projects gauge",
                "ipd_projects %d" % len(self.projects),
                "# HELP ipd_queue_depth Deployments waiting in queue.",
                "# TYPE ipd_queue_depth gauge",
                "ipd_queue_depth %d" % len(self.deployment_queue),
                "# HELP ipd_running_deployments Currently running deployments.",
                "# TYPE ipd_running_deployments gauge",
                "ipd_running_deployments %d" % self._running_count(),
                "# HELP ipd_uploads_total Total accepted uploads.",
                "# TYPE ipd_uploads_total counter",
                "ipd_uploads_total %d" % self._uploads,
                "# HELP ipd_processed_bytes_total Deployed image size, bytes.",
                "# TYPE ipd_processed_bytes_total counter",
                "ipd_processed_bytes_total %d" % processed,
                "# HELP ipd_uptime_seconds Service uptime.",
                "# TYPE ipd_uptime_seconds gauge",
                "ipd_uptime_seconds %d" % int(time.time() - self.start),
            ]

        return "\n".join(lines) + "\n"

    def cleanup(self) -> None:
        stamp = time.time()

        with self._lock:
            self.projects = {
                name: project
                for name, project in self.projects.items()
                if stamp - project.start < TTL and project.state() < 4
            }
