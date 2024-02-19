FROM nginx:stable

# nginx configs
COPY uwsgi_params /etc/nginx/uwsgi_params
COPY nginx.conf /etc/nginx/nginx.conf
COPY bytedeck.aws.conf /etc/nginx/sites-available/bytedeck.conf

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
