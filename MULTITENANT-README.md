# Multitenant architecture integration to hackerspace

- Django package used for mulitenant integration [django-tenant-schemas](https://django-tenant-schemas.readthedocs.io/en/latest/). Github link [here](https://github.com/bernardopires/django-tenant-schemas).

 - For celery, django package used is [tenant-schemas-celery](https://github.com/maciej-gol/tenant-schemas-celery).


## Single tenant vs Multitenant architecture
![img](https://miro.medium.com/max/1498/1*QjrjYFMxKjqakE1FWbIQGA.png)


## Configuration
----

- **Initial setup documentation [here](https://github.com/bernardopires/django-tenant-schemas#setup--documentation).**

- **Configure Tenant and Shared Applications -> [here](https://django-tenant-schemas.readthedocs.io/en/latest/install.html#configure-tenant-and-shared-applications)**

- ```.env``` file  -> ```WEB_URL``` for application base url.


> ### Tenant
> - Tenant application name - ```tenant```
> - Tenant model - ```tenant/Tenant```


## Populating public schema and a admin user for public schema on first run
----
```shell
$ bash init_public_schema.sh
```
