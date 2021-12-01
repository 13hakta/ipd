# IPD - Image Push and Deploy
==================

`ipd` - Receive app images and switch execution to new container.

## Concept

IPD is a small self-hosted deployment service for containerized
applications. A CI pipeline (or a developer) uploads a Docker image and a
deployment package over HTTP(S), and IPD runs the release on the target
server — no SSH access, no agent on build machines and no Docker registry
required.

The typical scenario:

1. CI builds a Docker image, saves it to a tar archive and packs it
   together with the deployment package (for example a `docker-compose.yml`
   and a `control.sh` script) into a single upload.
2. The pipeline POSTs the upload to `/upload` with an auth token and then
   polls `/status/$project/$deployment` until the deployment reports `ok`.
3. On the server IPD unpacks the upload, loads the image with `docker load`
   and hands control to the project's `control.sh`, which switches the
   running stack to the new version.

This fits best when you run a handful of services on your own hosts and
do not want a full Kubernetes/registry-based delivery stack: the server
may even be air-gapped from external registries, the only requirement is
that the CI can reach IPD over HTTPS.

Deployment logic is intentionally kept out of IPD itself: each project
provides its own `control.sh` with three actions (`check`, `prepare`,
`deploy`), so a release can be anything `docker-compose up` can express —
while IPD handles the delivery parts common to all projects: authenticated
uploads, queueing, timeouts, idempotency, status reporting, recovery after
restarts and monitoring hooks. A working example of `control.sh` and the
upload command line lives in the `example/` directory.

## Deploy flow

- Run `control.sh check`. Return 1 if success, any other means error.
- If check was erroneous run `control.sh prepare`.
- Run `control.sh deploy`. Return 1 if success, any other means error.

Standard way to deploy project: upload package and wait until its processed.
On destination server project folder should be accessible to write for daemon user.

## Queue semantics

- A newer upload of the same project **supersedes** an awaiting one: the old
  deployment is discarded (its files are removed) and later reports `changed` status.
- The queue is served **LIFO** by design: a newer package is a newer version,
  so it is considered more important than older ones.
- A deployment of a project that is already deploying waits in the queue and
  is started as soon as the project is free; it is never silently dropped.

## Endpoints

Destination path prefixed with `API_ROOT`.

| Endpoint | Method | Description | Variables |
| ------ | ------ | ------ | ------ |
| / | GET | Welcome message ||
| /list | GET | List projects ||
| /upload | POST | Upload deployment package | project - project name<br>image - image file<br>package - package file |
| /info | GET | Project information ||
| /stat | GET | IPD statistics ||
| /status/$project | GET | Deployment status | $project - project name |
| /status/$project/$deployment | GET | Deployment status | $project - project name<br>$deployment - deployment ID, returned in upload |
| /health | GET | Liveness check, no auth required ||
| /metrics | GET | Prometheus metrics, ADMIN role ||

## Environment variables for control.sh

| Name | Value |
| ------ | ------ |
| PATH | Inherits from parent process |
| DEPLOY | UUID of deployment |
| PROJECT | project name passed on upload |

## Idempotent uploads

Pass an `Idempotency-Key` header on upload to protect against retries
(after a network timeout, for example). Repeating an upload with the same
key for the same project returns the uuid of the already accepted
deployment instead of creating a new one:

```
curl -H "Authorization: $TOKEN" -H "Idempotency-Key: build-123" ...
```

## Installation

Requirements: Python 3.9 or newer, Docker and docker-compose on the host.

- Add user<br>`adduser ipd`
- Add user to docker group<br>`addgroup ipd docker`
- Create upload folder<br>`mkdir -p /srv/upload && chown ipd:ipd /srv/upload`
- Fill with required values and copy config<br>`cp .env.example /etc/default/ipd`
- Install virtualenv (Debian distro and derivatives)<br>`sudo apt install -y python3-venv`
- Setup virtualenv<br>`sudo python3 -m venv /opt/ipd`
- Create user file list<br>`touch /opt/ipd/users.txt && chown ipd:ipd /opt/ipd/users.txt`
- Activate virtualenv<br>`source /opt/ipd/bin/activate`
- Setup<br>`pip install ipd-1.1.0-py3-none-any.whl`
- Add the first ADMIN user (prints a token, shown once)<br>`sudo -u ipd /opt/ipd/bin/ipd user add ADMIN admin -f /opt/ipd/users.txt`
- Copy config to systemd services `ipd.service` to `/etc/systemd/system/ipd.service`
- Reload systemd config<br>`systemctl daemon-reload`
- Install service<br>`systemctl enable ipd.service`
- Start service<br>`systemctl start ipd.service`
- Verify the service is running<br>`systemctl status ipd.service` and<br>`curl http://127.0.0.1:9955/deploy/health` returns `ok`
- Add to `nginx` config
```
server {
...

    location /deploy {
        client_max_body_size 0;
        proxy_pass http://localhost:9955;
        proxy_http_version 1.1;
        proxy_redirect                      off;
        proxy_set_header Host               $host;
        proxy_set_header X-Real-IP          $remote_addr;
        proxy_set_header X-Forwarded-For    $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto  $scheme;
        proxy_read_timeout 1m;
        proxy_connect_timeout 1m;
    }
}
```

The `location /deploy` must match `API_ROOT` (default `/deploy`), and
`proxy_pass` must point to `WEBADDRESS:WEBPORT` (default `127.0.0.1:9955`).

- Your site is now ready to respond on `/deploy`

## Logs

The service logs to stderr which is collected by systemd journal.
No log file is created on disk.

- View logs<br>`journalctl -u ipd`
- Follow logs<br>`journalctl -u ipd -f`

## Health and monitoring

- Liveness check (no auth required)<br>`GET /deploy/health` returns `ok`
- Metrics (ADMIN role) in Prometheus text format<br>`GET /deploy/metrics`

The systemd unit uses `Type=notify` and `WatchdogSec=90`: the service
reports readiness to systemd and pings the watchdog, so a hung process
is restarted automatically. Orphaned upload files of deployments
interrupted by a restart are removed on the next start.

## Systemd sandbox and Docker

The unit runs the service inside a systemd sandbox, but Docker
deployments keep working because:

- Docker is accessed through `/var/run/docker.sock` (`AF_UNIX` is kept
  in `RestrictAddressFamilies`), so the `ipd` user only needs membership
  in the `docker` group — no capabilities are required. Containers are
  started by the system `dockerd`, which is not affected by the sandbox.
- `ProtectSystem=strict` is relaxed with `ReadWritePaths` covering
  `UPLOAD_DIR` and the project directories written by `control.sh`
  (the example script deploys to `/srv`, so the unit sets
  `ReadWritePaths=/srv /srv/upload`). If your project files live
  elsewhere, add their parent directory to `ReadWritePaths`.

Keep in mind that if the watchdog kills a hung service, the running
`control.sh` is killed with it (default `KillMode=control-group`);
leftover files are cleaned up by the recovery pass on next start.

## Managing users

Use the built-in CLI instead of editing the auth file by hand:

- Add a user and get a token<br>`ipd user add USER alice -f /opt/ipd/users.txt`
- Add a user with a known token<br>`ipd user add ADMIN bot -f /opt/ipd/users.txt --token MyToken`
- List users<br>`ipd user list -f /opt/ipd/users.txt`

The token is shown once on `add` (only its SHA-256 hash is stored).

## Upgrade

Run under root (the virtualenv in `/opt/ipd` is owned by root).

- Activate virtualenv<br>`source /opt/ipd/bin/activate`
- Stop service<br>`systemctl stop ipd.service` — the service waits for
  running deployments to finish (up to `SHUTDOWN_TIMEOUT` seconds)
- Remove old package<br>`pip uninstall ipd`
- Install new package<br>`pip install ipd-1.1.0-py3-none-any.whl`
- Start service<br>`systemctl start ipd.service`
- Verify<br>`systemctl status ipd.service` and recent logs<br>`journalctl -u ipd -n 50`

## Auth file structure

One user record per line.

`ROLE:username:sha256`

Supported roles: ADMIN, USER. Empty lines and lines starting with `#` are ignored.

Example to get hash of password:<br>`echo -n "mypassword" | sha256sum | cut -f 1 -d " "`

## Environment variables

Must be set through `/etc/default/ipd` (see `EnvironmentFile` in
`ipd.service`) or environment variables.

| Name | Default | Description |
| ------ | ------ | ------ |
| WEBADDRESS | 127.0.0.1 | Address to listen on |
| WEBPORT | 9955 | Port to listen on |
| UPLOAD_DIR | . | Upload directory |
| AUTH_DB | /opt/ipd/users.txt | User password file |
| API_ROOT | /deploy | API root |
| MAX_UPLOAD_SIZE | 10737418240 | Max size of upload request body, bytes (10 GiB) |
| CHECK_TIMEOUT | 1800 | `control.sh check` timeout, seconds |
| PREPARE_TIMEOUT | 1800 | `control.sh prepare` timeout, seconds |
| DEPLOY_TIMEOUT | 1800 | `control.sh deploy` timeout, seconds |
| SHUTDOWN_TIMEOUT | 60 | Max time to wait for running deployments on shutdown |

## Prepare dev environment

- Setup virtualenv<br>`python3 -m venv venv`
- Activate virtualenv<br>`source ./venv/bin/activate`
- Install app with dev dependencies<br>`pip install -e .[dev]`
- Install pre-commit hooks<br>`pre-commit install`
- Run linters manually (black, mypy)<br>`pre-commit run --all-files`
- Run tests<br>`pytest tests/`

## Return codes for deploy status

Request deploy status by retrieving url `https://$REMOTE_HOST/deploy/status/$PROJECT/$PROJECT_DEPLOYMENT`.

In return you retrieve states:

| Code | Description |
| ------ | ------ |
| await | Awaiting in queue |
| active | Deployment enrolling |
| ok | Deployment successful |
| no | No such project processed |
| changed | Another deployment added while processing |
| *another code* | Code number returned by deployment script |
