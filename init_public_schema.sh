echo -e "\n####################################"
echo "# CREATING PUBLIC SCHEMA..."
echo "####################################"
docker-compose run web python src/manage.py loaddata src/tenant/fixtures/tenants.json


echo -e "\n####################################"
echo "# POPULATING SUPER USER..."
echo "####################################"
docker-compose run web python src/manage.py loaddata src/tenant/fixtures/users.json
