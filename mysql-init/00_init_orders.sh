#!/bin/sh
set -e

mysql --default-character-set=utf8mb4 \
  -uroot \
  -p"${MYSQL_ROOT_PASSWORD}" \
  "${MYSQL_DATABASE}" \
  < /docker-entrypoint-initdb.d/sql/01_init_orders.sql
