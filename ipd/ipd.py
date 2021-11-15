# -*- coding: utf-8 -*-
import logging
import os
import sys
from flask import Flask, request
from waitress import serve

from .auth import load_db, require_role
from .deployment import Deployment
from .manager import ProjectManager
from .svcthread import ServiceThread
from .utils import allowed_file, valid_project


def create_app(
    upload_dir: str = None,
    auth_db: str = None,
    api_root: str = None,
    max_upload_size: int = None,
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

    @app.route(api_root)
    def home():
        return "Image push & Deploy\n"

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


def main():
    logging.info("Start app")
    web_address = os.environ.get("WEBADDRESS", "127.0.0.1")
    web_port = int(os.environ.get("WEBPORT", "9955"))

    app = create_app()

    service = ServiceThread(app.extensions["project_manager"])
    service.start()

    serve(app, host=web_address, port=web_port)
    logging.info("Stop app")
    return None


if __name__ == "__main__":
    main()
