# -*- coding: utf-8 -*-

from threading import RLock
import logging
import time

from .project import Project

TTL = 86400
QUEUE_MAX = 200
TASKS_MAX = 5


class ProjectManager:
    def __init__(self):
        self.deployment_queue = []
        self.projects = {}
        self._lock = RLock()
        self._uploads = 0

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

    def get_state(self, project: str, deployment_uuid: str = None) -> str:
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

    def cleanup(self) -> None:
        stamp = time.time()

        with self._lock:
            self.projects = {
                name: project
                for name, project in self.projects.items()
                if stamp - project.start < TTL and project.state() < 4
            }
