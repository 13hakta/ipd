# -*- coding: utf-8 -*-
import os
import logging
from flask import Flask, request
from werkzeug.utils import secure_filename
from waitress import serve

from .auth import require_role, load_db
from .manager import ProjectManager
from .deployment import Deployment
from .svcthread import ServiceThread
from .utils import *

app = Flask(__name__)

# Load environment
UPLOAD_DIR = os.environ.get("UPLOAD_DIR", ".")
AUTH_DB = os.environ.get("AUTH_DB", "users.txt")
LOG_DIR = os.environ.get("LOG_DIR", ".")
API_ROOT = os.environ.get("API_ROOT", "/deploy")

# Init logging
logging.basicConfig(
    format="%(asctime)s %(levelname)s %(message)s",
    filename=f"{LOG_DIR}/ipd.log",
    level=logging.DEBUG,
    datefmt="%d.%m.%y %H:%M:%S",
)

load_db(AUTH_DB)

project_manager = ProjectManager()

service = ServiceThread(project_manager)
service.start()


@app.route(API_ROOT)
def home():
    return "Image push & Deploy\n"


@app.route(API_ROOT + "/list", methods=["GET"])
@require_role("ADMIN")
def get_list(user):
    return project_manager.list()


@app.route(API_ROOT + "/stat", methods=["GET"])
@require_role("ADMIN")
def get_stat(user):
    return project_manager.stat()


@app.route(API_ROOT + "/upload", methods=["POST"])
@require_role()
def upload_file(user):
    project = request.form["project"]

    if not project:
        logging.error("No project specified")
        return "err", 400

    logging.debug(
        "[%s:%s] Request deploy from %s",
        project,
        user,
        request.environ.get("HTTP_X_REAL_IP", request.remote_addr),
    )

    version = request.form.get("version", None)

    code = gen_code()

    upload_folder = UPLOAD_DIR + "/" + project + code
    os.mkdir(upload_folder)

    # Process package file
    if "package" not in request.files:
        logging.error("[%s] No package", project)
        return "err", 400

    pkg = request.files["package"]
    package_file = UPLOAD_DIR + "/package.tar" + code
    pkg.save(package_file)

    # Process image file
    if "image" not in request.files:
        logging.error("[%s] No image", project)
        return "err", 400

    img = request.files["image"]

    if img.filename == "":
        logging.error("[%s] Empty image name", project)
        return "err", 400

    if img and allowed_file(img.filename):
        image_file = f"{upload_folder}/{secure_filename(img.filename)}"
        img.save(image_file)
    else:
        logging.error("[%s] Cant save image", project)
        return "err", 400

    deployment = Deployment(
        project, upload_folder, package_file, image_file, version=version
    )

    if deployment.check() != 0:
        logging.error("[%s] Deployment check failed", project)
        return "err", 400

    logging.info("[%s:%s] Add deploy by %s", project, deployment.uuid, user)

    result = project_manager.add(deployment)

    if result == 0:
        return deployment.uuid

    logging.error("[%s] Add deployment failed %d", project, result)
    return "err", 400


@app.route(API_ROOT + "/info/<string:name>", methods=["GET"])
@require_role()
def get_info(user, name):
    project = project_manager.get(name)

    return project.info() if project else "no"


@app.route(API_ROOT + "/status/<string:project>", methods=["GET"])
@require_role()
def get_status(user, project):
    return project_manager.get_state(project)


@app.route(API_ROOT + "/status/<string:project>/<string:deploy>", methods=["GET"])
@require_role()
def get_status_deploy(user, project, deploy):
    return project_manager.get_state(project, deploy)


def main():
    logging.info("Start app")
    WEBADDRESS = os.environ.get("WEBADDRESS", "127.0.0.1")
    WEBPORT = int(os.environ.get("WEBPORT", "8080"))
    serve(app, host=WEBADDRESS, port=WEBPORT)
    logging.info("Stop app")
    return None


if __name__ == "__main__":
    main()
