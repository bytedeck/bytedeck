psql -U postgres -c "DROP DATABASE IF EXISTS temp_db"
psql -U postgres -c "CREATE DATABASE temp_db"
psql -U postgres temp_db < /dumps/$1
psql -U postgres -d temp_db -c "DROP TABLE IF EXISTS django_site CASCADE"
psql -U postgres -d temp_db -c "ALTER SCHEMA public RENAME TO $2"
pg_dump -U postgres -d temp_db -n $2 > dump.pgsql
psql -U postgres -c "DROP DATABASE temp_db"
psql -U postgres -c "DROP SCHEMA IF EXISTS $2 CASCADE"
psql -U postgres postgres < dump.pgsql
rm dump.pgsql
