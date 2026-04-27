FROM nginx:alpine
COPY index.html /usr/share/nginx/html/
COPY app.js /usr/share/nginx/html/
COPY style.css /usr/share/nginx/html/
EXPOSE 8080
CMD sed -i 's/listen\s*80;/listen 8080;/g' /etc/nginx/conf.d/default.conf && nginx -g 'daemon off;'
