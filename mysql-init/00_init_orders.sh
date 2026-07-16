#!/bin/sh
set -e

mysql --default-character-set=utf8mb4 \
  -uroot \
  -p"${MYSQL_ROOT_PASSWORD}" \
  "${MYSQL_DATABASE}" \
  < /docker-entrypoint-initdb.d/sql/01_init_orders.sql

mysql --default-character-set=utf8mb4 \
  -uroot \
  -p"${MYSQL_ROOT_PASSWORD}" \
  "${MYSQL_DATABASE}" <<SQL
CREATE USER IF NOT EXISTS '${MYSQL_WREN_USER}'@'%' IDENTIFIED BY '${MYSQL_WREN_PASSWORD}';
GRANT SELECT, SHOW VIEW ON \`${MYSQL_DATABASE}\`.* TO '${MYSQL_WREN_USER}'@'%';
FLUSH PRIVILEGES;
SQL
