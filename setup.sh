# Initial setup of hackerspace development environment

# Assuming docker and docker-compose is installed

# Create the image defined in Dockerfile
echo -e "\n####################################"
echo "# BUIDING DOCKER IMAGE..."
echo "####################################"
docker-compose build

# Migrations are already completed in docker-compose.yml web definitaon, so prob notneeded here
echo -e "\n####################################"
echo "# CREATING DATABASE..."
echo "####################################"
docker-compose run web python src/manage.py migrate

echo -e "\n####################################"
echo "# LOADING INITIAL DATA..."
echo "####################################"
docker-compose run web python src/manage.py loaddata src/initial_data

echo -e "\n####################################"
echo "# CREATING SUPERUSER..."
echo "# Enter username and password to create admin user."
echo "####################################"
docker-compose run web python src/manage.py createsuperuser

echo -e "\n####################################"
echo "# CREATING CACHE TABLE..."
echo "####################################"
docker-compose run web python src/manage.py createcachetable

echo -e "\n####################################"
echo "# TESTING PROJECT..."
echo "# If this gives errors failures (Es or Fs), something probably went wrong =("
echo "####################################"
docker-compose run web python src/manage.py test src

echo -e "\n####################################"
echo "# PROJECT INITIATIED!"
echo "#  - Run \"docker-compose up\" from this directory to run the project."
echo "#  - Then go to 127.0.0.1:8000 in your web browser and sign in with the admin user you just created."
echo "####################################"