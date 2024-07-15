# Production Server Notes

## SSL Certificates

Installed via [cerbot (snap package)](https://certbot.eff.org/instructions?ws=nginx&os=ubuntufocal&tab=wildcard) and [cerbot-dns-route5](https://certbot-dns-route53.readthedocs.io/en/stable/) and auto-renewed via systemd

### certbot

Once set up, the certbot package's systemd timer will try to auto renew the certificates.

1. `systemctl status snap.certbot.renew.timer` which runs twice a day at 0900 and 2200 UTC and triggers the renew service
2. `systemctl status snap.certbot.renew.service` which executes `/usr/bin/snap run --timer="00:00~24:00/2" certbot.renew` which runs the renew command twice a day as a one shot

Not exactly sure why both timer and renew services go twice a day.  And the renew service seems to be a random picked times (~) for some reason.  See snap renew docs.

However, even if this succeeds, the new certificates won't automatically be available to nginx, so we need to overide the renew service to add some additional commands to reload nginx.  If the override is properly located, it should appear when you get the status of the snap.certbot.renew.service.

3. `cat /etc/systemd/system/snap.certbot.renew.service.d/snap.certbot.renew.service.override.conf`


## Deployment workflow -- OLD

### Stack
- nginx
- uwsgi
- docker (docker-compose)
- git

### Files info
- Nginx config is available on: ``/etc/nginx/sites-available/hackerspace.conf``
- Application directory is on: ``/usr/share/nginx/hackerspace``
- Application should be running as www-data user

**Note, when media uploads and static files volumes of the application's container are mapped to host, the application container by default runs on root user, and the files created on the mounts will automatically become root ownership files, which will not be accessible from browser requests.**

**To override this phenomenon user's $UID and $GID is explicitly passed on `web` service of docker compose so that the files created under the process are owned by that $UID and $GID. This are set by**
```shell script
    $ export WUID=<user_id>
    $ export WGID=<group_id>
```
_`<user_id>` & `<group_id>` are the `uid` and `gid` of the user preferred to run container with_

_run these commands before running any `docker-compose` commands_

_To check which user is running which container_
```shell script
docker inspect $(docker ps -aq) --format '{{.Config.User}} {{.Name}}'
```


### Production deployment steps
- Step 1: Go to application directory: ``/usr/share/nginx/hackerspace``
- Step 2: Set WUID and WGID variables:
```shell script
    $ export WUID=<user_id>
    $ export WGID=<group_id>
```
_`<user_id>` & `<group_id>` are the `uid` and `gid` of the user preferred to run container with_

- Step 3: Check the status of containers by ``docker compose ps``
- Step 4: To deploy changes, use ``docker compose down`` then ``git pull``
- Step 5: Run the application using ``docker compose build && docker compose up -d``


### Workflow
- ``uwsgi`` is used to run the django application inside docker container
- ``nginx`` reverse proxy is configured to point the docker django application mapped port
- static and media files are served by ``nginx`` itself by pointing the url to the static and media directory of the application ie. ``/var/www/bytedeck/static`` and ``/var/www/bytedeck/media``
- For static web hosting, check docker compose location of volume map for setting `STATIC_ROOT`. Current configuration suits for `STATIC_ROOT='/var/static'`.


### Production setup
- settings can be found inside ``src/hackerspace_online/settings``
- for production settings create a file named ``production_hackerspace.py`` inside settings directory which should include ``src/hackerspace_online/settings/base.py`` on top and extend those configuration


### SSL setup using let's encrypt
- https://certbot.eff.org/
- https://ssl-config.mozilla.org/#server=nginx&version=1.17.7&config=modern&openssl=1.1.1d&guideline=5.4
- Get an A+ here: https://www.ssllabs.com/ssltest/

### Redis stuff

- Resolve several warnings wth this this systemd unit: https://gist.github.com/tylerecouture/cf6a88c4dae6dd19872964e3c5509db7


