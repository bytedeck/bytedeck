FROM nginx:stable

# nginx configs
COPY uwsgi_params /etc/nginx/uwsgi_params
COPY nginx.conf /etc/nginx/nginx.conf

# Render the site config from a single template shared by production and
# staging. DOMAIN is REQUIRED and has no default on purpose: it is supplied per
# environment from ROOT_DOMAIN via docker-compose.prod.aws.yml (bytedeck.com for
# production, bytedeck-staging.com for staging), so hardcoding a default here
# would be misleading and could silently ship the wrong domain. The guard below
# fails the build loudly if it is missing. envsubst is restricted to '${DOMAIN}'
# so it substitutes only the domain and leaves nginx's own
# $host/$scheme/$request_uri/$1 variables intact.
ARG DOMAIN
COPY bytedeck.conf.template /tmp/bytedeck.conf.template
RUN test -n "$DOMAIN" || { echo "ERROR: DOMAIN build arg is required (normally supplied from ROOT_DOMAIN by docker-compose.prod.aws.yml; e.g. --build-arg DOMAIN=bytedeck.com)." >&2; exit 1; } \
    && mkdir -p /etc/nginx/sites-available \
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

# Static maintenance page served by nginx when the app backend is unreachable
# (see the error_page directive in bytedeck.conf.template). Baked into the image
# so it is always available, independent of the app containers or mounted
# volumes. COPY leaves it world-readable (644), so the non-root nginx worker can
# serve it.
COPY maintenance/ /var/www/maintenance/

CMD ["nginx", "-g", "daemon off;"]
