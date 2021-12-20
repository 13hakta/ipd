#!/bin/sh

DEPLOY_KEY=qwe
PROJECT=backend
REMOTE_HOST=localhost:9955
EXTRA_FILES="control.sh docker-compose.yml"
IMAGE_FILE="docker-images.tar.gz"
TTL=1200

PROJECT_DEPLOYMENT=$(tar -cf - $EXTRA_FILES | curl \
    -X POST \
    -H "Authorization: $DEPLOY_KEY" \
    -F "project=$PROJECT" \
    -F "image=@$IMAGE_FILE" \
    -F 'package=@-' \
    http://$REMOTE_HOST/deploy/upload)

if [ "$PROJECT_DEPLOYMENT" = "err" ]; then
    echo Add failed
    exit 1
fi

START_TIME=$(date +%s)
END_TIME=$((START_TIME+TTL))

while [ $(date +%s) -lt $END_TIME ]; do
    PROJECT_DEPLOY_STATUS=$(curl \
        -H "Authorization: $DEPLOY_KEY" -s \
        http://$REMOTE_HOST/deploy/status/$PROJECT/$PROJECT_DEPLOYMENT)

    case "$PROJECT_DEPLOY_STATUS" in
        ok) echo "Successful"; exit 0 ;;
        await)  sleep 10 ;;
        active) sleep 5 ;;
        no) echo "No project"; exit 2 ;;
        *) echo "Wrong value: $PROJECT_DEPLOY_STATUS"; exit 3
    esac
done

echo "Timeout"
exit 4
