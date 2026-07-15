FROM nginx:stable

# nginx configs
COPY uwsgi_params /etc/nginx/uwsgi_params
COPY nginx.conf /etc/nginx/nginx.conf

# Render the site config from a single template shared by production and
# staging. envsubst is restricted to '${DOMAIN}' so it substitutes only the
# domain and leaves nginx's own $host/$scheme/$request_uri/$1 variables intact.
# DOMAIN is a build arg wired to ROOT_DOMAIN (see docker-compose.prod.aws.yml);
# the build happens per-host, so each environment bakes in its own domain.
ARG DOMAIN=bytedeck.com
COPY bytedeck.conf.template /tmp/bytedeck.conf.template
RUN mkdir -p /etc/nginx/sites-available \
    && envsubst '${DOMAIN}' < /tmp/bytedeck.conf.template > /etc/nginx/sites-available/bytedeck.conf \
    && rm /tmp/bytedeck.conf.template

# SSL details
# SSL now provided via mounted container during runtime, so cerbot can update from host
#COPY cert.pem /etc/letsencrypt/live/bytedeck.com/cert.pem
#COPY chain.pem /etc/letsencrypt/live/bytedeck.com/chain.pem
#COPY fullchain.pem /etc/letsencrypt/live/bytedeck.com/fullchain.pem
#COPY privkey.pem /etc/letsencrypt/live/bytedeck.com/privkey.pem
#COPY ssl-dhparams.pem /etc/letsencrypt/ssl-dhparams.pem

RUN mkdir -p /etc/nginx/sites-enabled/ \
    && ln -s /etc/nginx/sites-available/bytedeck.conf /etc/nginx/sites-enabled/
ARG WUID
ARG WGID
RUN touch /var/run/nginx.pid && \
  chown -R ${WUID}:${WGID} /var/run/nginx.pid && \
  chown -R ${WUID}:${WGID} /var/cache/nginx && \
  chown -R ${WUID}:${WGID} /etc/nginx/conf.d/
RUN chmod -R 755 /etc/nginx/sites-enabled
#RUN chmod -R 755 /etc/letsencrypt/
RUN mkdir -p /var/www/bytedeck/static

CMD ["nginx", "-g", "daemon off;"]
