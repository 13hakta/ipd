# -*- coding: utf-8 -*-
import logging
import os
import signal
import sys
from threading import Event, Thread
from typing import Optional
from flask import Flask, request
from waitress.server import create_server

from .auth import load_db, require_role
from .deployment import Deployment
from .manager import ProjectManager
from .sdnotify import WatchdogThread, sd_notify
from .svcthread import ServiceThread
from .utils import allowed_file, valid_project

IDEMPOTENCY_KEY_MAX = 128


def create_app(
    upload_dir: Optional[str] = None,
    auth_db: Optional[str] = None,
    api_root: Optional[str] = None,
    max_upload_size: Optional[int] = None,
) -> Flask:
    """Create and configure Flask application"""
    if upload_dir is None:
        upload_dir = os.environ.get("UPLOAD_DIR", ".")
    if auth_db is None:
        auth_db = os.environ.get("AUTH_DB", "users.txt")
    if api_root is None:
        api_root = os.environ.get("API_ROOT", "/deploy")
    if max_upload_size is None:
        max_upload_size = int(
            os.environ.get("MAX_UPLOAD_SIZE", 10 * 1024 * 1024 * 1024)
        )

    # Init logging: write to stderr, let systemd journal collect it.
    # No log file to create or rotate on disk.
    logging.basicConfig(
        format="%(asctime)s %(levelname)s %(message)s",
        stream=sys.stderr,
        level=logging.DEBUG,
        datefmt="%d.%m.%y %H:%M:%S",
    )

    app = Flask(__name__)

    # Reject request body larger than max_upload_size (10 GiB by
    # default) before anything is written to disk.
    app.config["MAX_CONTENT_LENGTH"] = max_upload_size

    load_db(auth_db)

    project_manager = ProjectManager()
    app.extensions["project_manager"] = project_manager

    # Clean up leftovers of deployments interrupted by a restart
    project_manager.recover(upload_dir)

    @app.route(api_root)
    def home():
        return "Image push & Deploy\n"

    @app.route(api_root + "/health", methods=["GET"])
    def health():
        return "ok\n"

    @app.route(api_root + "/metrics", methods=["GET"])
    @require_role("ADMIN")
    def get_metrics(user):
        return project_manager.metrics(), 200, {"Content-Type": "text/plain"}

    @app.route(api_root + "/list", methods=["GET"])
    @require_role("ADMIN")
    def get_list(user):
        return project_manager.list()

    @app.route(api_root + "/stat", methods=["GET"])
    @require_role("ADMIN")
    def get_stat(user):
        return project_manager.stat()

    @app.route(api_root + "/upload", methods=["POST"])
    @require_role()
    def upload_file(user):
        project = request.form.get("project", "")

        if not valid_project(project):
            logging.error("Invalid project name: %r", project)
            return "err", 400

        logging.debug(
            "[%s:%s] Request deploy from %s",
            project,
            user,
            request.environ.get("HTTP_X_REAL_IP", request.remote_addr),
        )

        version = request.form.get("version")

        # Idempotent retries: same Idempotency-Key for the same project
        # returns the uuid of the already accepted deployment.
        idempotency_key = (request.headers.get("Idempotency-Key") or "").strip()

        if idempotency_key:
            if (
                len(idempotency_key) > IDEMPOTENCY_KEY_MAX
                or not idempotency_key.isprintable()
            ):
                logging.error("[%s] Invalid idempotency key", project)
                return "err", 400

            existing = project_manager.find_idempotent(project, idempotency_key)

            if existing:
                logging.info(
                    "[%s] Idempotent retry: return existing %s",
                    project,
                    existing.uuid,
                )
                return existing.uuid

        # Validate the whole request before writing anything to disk,
        # so failed uploads leave no garbage behind.

        if "package" not in request.files:
            logging.error("[%s] No package", project)
            return "err", 400

        pkg = request.files["package"]

        if "image" not in request.files:
            logging.error("[%s] No image", project)
            return "err", 400

        img = request.files["image"]

        if not img.filename:
            logging.error("[%s] Empty image name", project)
            return "err", 400

        if not allowed_file(img.filename):
            logging.error("[%s] Cant save image", project)
            return "err", 400

        deployment = Deployment(project, upload_dir, img.filename, version=version)
        deployment.idempotency_key = idempotency_key or None

        try:
            deployment.save(pkg, img)
        except OSError as exc:
            logging.error("[%s] Cant store upload: %s", project, exc)
            deployment.discard()
            return "err", 400

        if deployment.check() != 0:
            logging.error("[%s] Deployment check failed", project)
            deployment.discard()
            return "err", 400

        logging.info("[%s:%s] Add deploy by %s", project, deployment.uuid, user)

        result = project_manager.add(deployment)

        if result == 0:
            return deployment.uuid

        logging.error(
            "[%s:%s] Add deployment failed %d", project, deployment.uuid, result
        )
        deployment.discard()
        return "err", 400

    @app.route(api_root + "/info/<string:name>", methods=["GET"])
    @require_role()
    def get_info(user, name):
        project = project_manager.get(name)

        return project.info() if project else "no"

    @app.route(api_root + "/status/<string:project>", methods=["GET"])
    @require_role()
    def get_status(user, project):
        return project_manager.get_state(project)

    @app.route(api_root + "/status/<string:project>/<string:deploy>", methods=["GET"])
    @require_role()
    def get_status_deploy(user, project, deploy):
        return project_manager.get_state(project, deploy)

    return app


def main(argv=None) -> None:
    if argv is None:
        argv = sys.argv[1:]

    if argv and argv[0] == "user":
        from .cli import user_cli

        raise SystemExit(user_cli(argv[1:]))

    web_address = os.environ.get("WEBADDRESS", "127.0.0.1")
    web_port = int(os.environ.get("WEBPORT", "9955"))
    shutdown_timeout = float(os.environ.get("SHUTDOWN_TIMEOUT", "60"))

    app = create_app()
    manager = app.extensions["project_manager"]

    service = ServiceThread(manager)
    service.start()

    watchdog = WatchdogThread()
    watchdog.start()

    server = create_server(app, host=web_address, port=web_port)
    server_thread = Thread(target=server.run, daemon=True)
    server_thread.start()

    sd_notify("READY=1")
    logging.info("Start app")

    done = Event()

    def handle_signal(signum, frame):
        done.set()

    signal.signal(signal.SIGTERM, handle_signal)
    signal.signal(signal.SIGINT, handle_signal)

    done.wait()

    logging.info(
        "Stop app: waiting up to %ds for running deployments", int(shutdown_timeout)
    )
    sd_notify("STOPPING=1")

    # Stop accepting new requests, in-flight ones finish on their own
    server.close()
    server_thread.join(5)

    # Wait for running deployments, then stop background loops
    manager.stop(shutdown_timeout)
    service.stop_event.set()
    watchdog.stop_event.set()

    logging.info("Stopped")
    return None


if __name__ == "__main__":
    main()
