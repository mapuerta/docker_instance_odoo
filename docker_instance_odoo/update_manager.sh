#!/bin/bash


dbname="produccion"
db_host=$(docker inspect --format='{{range .NetworkSettings.Networks}}{{.IPAddress}}{{end}}' yoytec_server_db)
[ -z $db_host ] && db_host='127.0.0.1'
workerdir='/home/odoo/docker_instance_odoo/docker_instance_odoo'
fileyml='${workerdir}/docker-compose.yml'

python3 /usr/bin/manager_instance.py -f ${fileyml} -s ${db_host} -d ${dbname} -w ${workerdir} $@
