# -*- coding: utf-8 -*-

from threading import Lock
import time

from .project import Project


TTL = 86400
QUEUE_MAX = 200
TASKS_MAX = 5


class ProjectManager:
    def __init__(self):
        self.deployment_queue = []
        self.projects = {}
        self._lock = Lock()
        self._uploads = 0

    def lock(self) -> None:
        self._lock.acquire(True)

    def unlock(self) -> None:
        self._lock.release()

    def process(self, deployment) -> int:
        deployment.manager = self

        if deployment.project not in self.projects:
            project = Project()
            self.projects[deployment.project] = project

        return self.projects[deployment.project].process(deployment)

    def next(self) -> None:
        self.lock()

        while self.deployment_queue:
            if self.get_current_running() < TASKS_MAX:
                self.process(self.deployment_queue.pop())
            else:
                break

        self.unlock()

    def add(self, deployment) -> int:
        if len(self.deployment_queue) >= QUEUE_MAX:
            return 1

        self.lock()

        found = False

        if self.deployment_queue:
            # Replace awaiting deployments
            for idx, item in enumerate(self.deployment_queue):
                if item.project == deployment.project:
                    self.deployment_queue[idx] = deployment
                    found = True
                    break

        if not found:
            self.deployment_queue.append(deployment)

        self._uploads += 1

        self.unlock()

        self.next()

        return 0

    def get_current_running(self) -> int:
        result = 0

        for project in self.projects:
            if 0 < self.projects[project].state() < 4:
                result += 1

        return result

    def get(self, project: str) -> Project:
        return self.projects[project] if project in self.projects else None

    def get_state(self, project: str, deployment_uuid: str = None) -> str:
        for item in self.deployment_queue:
            if item.uuid == deployment_uuid:
                return "await"

            if not deployment_uuid and item.project == project:
                return "await"

        project_obj = self.get(project)

        if project_obj:
            if deployment_uuid:
                if (
                    project_obj.deployment
                    and project_obj.deployment.uuid != deployment_uuid
                ):
                    return "changed"
        else:
            return "no"

        return project_obj.state_code()

    def list(self) -> str:
        return "\n".join([x for x in self.projects])

    def stat(self) -> dict:
        return {
            "projects": len(self.projects),
            "queue": len(self.deployment_queue),
            "uploads": self._uploads,
        }

    def cleanup(self) -> None:
        stamp = time.time()
        remain = 0
        removed = 0

        filtered_projects = {}

        self.lock()

        for project in self.projects:
            project_obj = self.projects[project]

            if stamp - project_obj.start < TTL and project_obj.state() < 4:
                filtered_projects[project] = project_obj
                remain += 1
            else:
                removed += 1

        self.projects = filtered_projects

        self.unlock()
