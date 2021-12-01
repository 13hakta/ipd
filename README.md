# IPD - Image Push and Deploy
==================

`ipd` - Receive app images and switch execution to new container.

## Deploy flow

- Run `control.sh check`. Return 1 if success, any other means error.
- If check was erroneous run `control.sh prepare`.
- Run `control.sh deploy`. Return 1 if success, any other means error.

Standard way to deploy project: upload package and wait until its processed.
On destination server project folder should be accessible to write for daemon user.

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

## Environment variables for control.sh

| Name | Value |
| ------ | ------ |
| PATH | Inherits from parent process |
| DEPLOY | UUID of deployment |
| PROJECT | project name passed on upload |

## Installation

- Add user<br>`adduser ipd`
- Add user to docker group<br>`addgroup ipd docker`
- Create log<br>`touch /var/log/ipd.log && chown ipd.ipd /var/log/ipd.log`
- Create upload folder<br>`mkdir /srv/upload && chown ipd.ipd /srv/upload`
- Fill with required values and copy config<br>`cp .env.example /etc/default/ipd`
- Install virtualenv (Debian distro and derivatives)<br>`sudo apt install -y python3-venv`
- Setup virtualenv<br>`sudo python3 -m venv /opt/ipd`
- Create user file list<br>`touch /opt/ipd/users.txt && chown ipd.ipd /opt/ipd/users.txt` and add users
- Activate virtualenv<br>`source /opt/ipd/bin/activate`
- Setup<br>`pip install ipd-1.0.0-py3-none-any.whl`
- Copy config to systemd services `ipd.service` to `/etc/systemd/system/ipd.service`
- Install service<br>`systemctl enable ipd.service`
- Start service<br>`systemctl start ipd.service`
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
- Your site is now ready to respond on `/deploy`

## Upgrade

- Activate virtualenv<br>`source /opt/ipd/bin/activate`
- Stop service<br>`systemctl stop ipd.service`
- Remove old package<br>`pip uninstall ipd`
- Install new package<br>`pip install ipd-1.0.0-py3-none-any.whl`
- Start service<br>`systemctl start ipd.service`

## Auth file structure

One user record per line.

`ROLE:username:sha256`

Supported roles: ADMIN, USER.

Example to get hash of password:<br>`echo -n "mypassword" | sha256sum | cut -f 1 -d " "`

## Environmant variables

Must be set through `/etc/ipd.conf` or environment variables.

| Name | Default | Description |
| ------ | ------ | ------ |
| LOG_DIR | . | Log directory |
| UPLOAD_DIR | . | Upload directory |
| AUTH_DB | /opt/ipd/users.txt | User password file |
| API_ROOT | /deploy | API root |

## Prepare dev environment

- Setup virtualenv<br>`python3 -m venv venv`
- Activate virtualenv<br>`source ./venv/bin/activate`
- Prepare app<br>`python3 setup.py develop`

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
