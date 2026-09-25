#!/bin/sh

DEPLOY_KEY=qwe
REMOTE_HOST=localhost:9955
BASE_URL=http://$REMOTE_HOST
PROJECT=backend

curl -X GET -H "Authorization: $DEPLOY_KEY" \
    $BASE_URL/deploy

curl -X GET -H "Authorization: $DEPLOY_KEY" \
    $BASE_URL/deploy/stat

echo INFO

curl -X GET -H "Authorization: $DEPLOY_KEY" \
    $BASE_URL/deploy/info/$PROJECT

echo
echo STATE

curl -X GET -H "Authorization: $DEPLOY_KEY" \
    $BASE_URL/deploy/status/$PROJECT

echo
