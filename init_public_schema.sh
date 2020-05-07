echo -e "\n####################################"
echo "# CREATING PUBLIC SCHEMA..."
echo "####################################"
docker-compose run --rm web python src/manage.py loaddata src/tenant/fixtures/tenants.json


echo -e "\n####################################"
echo "# POPULATING SUPER USER..."
echo "####################################"
docker-compose run --rm web python src/manage.py loaddata src/tenant/fixtures/users.json


echo -e "\n####################################"
echo "# POPULATING SITES MODEL..."
echo "####################################"
docker-compose run --rm web python src/manage.py loaddata src/initial_data.json
