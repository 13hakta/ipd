#!/bin/sh

ACTION=$1
APP_DIR=/srv/$PROJECT

check() {
    echo Check

    if ! command -v docker-compose &> /dev/null; then
        echo "docker-compose could not be found"
        exit 2
    fi

    exit 1
}

prepare() {
    echo Prepare

    mkdir -p $APP_DIR
}

deploy() {
    echo Deploy

    gzip -dc < docker-images.tar.gz | docker load

    if [ $? != 0 ]; then
      echo "Unable to load image"
      exit 2
    fi

    cp -r docker-compose.yml $APP_DIR/
    cd $APP_DIR

    docker-compose up -d -t 0 || exit 3

    echo Done
    exit 1
}

if [ -z "$ACTION" ]; then
    echo "$0 check|prepare|deploy"
else
    case "$ACTION" in
        check) check     ;;
        prepare) prepare ;;
        deploy) deploy   ;;
        *) echo "Wrong command"
           exit 1
    esac
fi
