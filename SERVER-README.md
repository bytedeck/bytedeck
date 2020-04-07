## Deployment workflow

### Stack
- nginx
- uwsgi
- docker (docker-compose)
- git

### Steps
- configure nginx in ``/etc/nginx/sites-available/hackerspace.conf``
- go to application directory ``/usr/share/nginx/hackerspace``
- to run application for the first time, use ``docker-compose build && docker-compose up -d``
- check the status of containers by ``docker-compose ps``
- to deploy changes, use ``docker-compose down`` then ``git pull``
- next run the application using ``docker-compose build && docker-compose up -d``


### Workflow
- ``uwsgi`` is used to run the django application inside docker container
- ``nginx`` reverse proxy is configured to point the docker django application mapped port
- static and media files are served by ``nginx`` itself by pointing the url to the static and media directory of the application ie. ``/var/www/bytedeck/static`` and ``/var/www/bytedeck/media``


### Production setup
- settings can be found inside ``src/hackerspace_online/settings``
- for production settings create a file named ``production_hackerspace.py`` inside settings directory which should include ``src/hackerspace_online/settings/base.py`` on top and extend those configuration


### SSL setup using let's encrypt

- setup steps are followed accordingly as mentioned [here](https://www.howtoforge.com/tutorial/nginx-with-letsencrypt-ciphersuite/).
