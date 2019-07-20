# Initial setup of hackerspace development environment

# Assuming docker and docker-compose is installed

# Create the image defined in Dockerfile
docker build .

# Migrations are already completed in docker-compose.yml web definition, so prob notneeded here
echo "CREATING DATABASE..."
docker-compose run web python src/manage.py migrate

echo "LOADING INITIAL DATA..."
docker-compose run web python src/manage.py loaddata src/initial_data

echo "CREATING SUPERUSER..."
echo "Enter username and password to create admin user."
docker-compose run web python src/manage.py createsuperuser

echo "CREATING CACHE TABLE..."
docker-compose run web python src/manage.py createcachetable

echo "PROJECT INITIATIED!"
echo "run \"docker-compose up\" from this directory to run the project."
echo "then go to 127.0.0.1:8000 in your web browser and sign in with the admin user you just created."