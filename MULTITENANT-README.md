# Multitenant architecture integration to hackerspace

- Django package used for mulitenant integration [django-tenant-schemas](https://django-tenant-schemas.readthedocs.io/en/latest/). Github link [here](https://github.com/bernardopires/django-tenant-schemas).

 - For celery, django package used is [tenant-schemas-celery](https://github.com/maciej-gol/tenant-schemas-celery).


## Multitenant architecture
![img](https://rubygarage.s3.amazonaws.com/uploads/article_image/file/527/multi-tenant-saas-app-with-ruby-on-rails-shared-database-architecture.jpg.png)
Multitenancy is an interesting problem to solve and there are basically three solutions:

1. Isolated Approach: Separate Databases. Each tenant has it’s own database.
2. Semi Isolated Approach: Shared Database, Separate Schemas. One database for all tenants, but one schema per tenant.
3. Shared Approach: Shared Database, Shared Schema. All tenants share the same database and schema. There is a main tenant-table, where all other tables have a foreign key pointing to.

On this application, Semi Isolated Approach has been followed.

### How does it work?
Tenants are identified via their host name (i.e tenant.domain.com). This information is stored on a table on the public schema. Whenever a request is made, the host name is used to match a tenant in the database. If there’s a match, the search path is updated to use this tenant’s schema. So from now on all queries will take place at the tenant’s schema.
*Tenant* model is used who store tenant information.

#### How to create tenants?
1. Login to superadmin area http://url.com/admin.
2. Click on Tenant.
3. Create Tenant (note subdomain is automatically generated from the name).
4. When the tenant is created a super admin user for that tenant is automatically created by the system (reach out to admin for default user and pw).
5. After these steps https://tenant1.url.com/ should be up and running.


#### User Types in MultiTenancy
1. is_superadmin -> This user exists in all the schemas. However, the user on public schema is a bit special because they can create Tenant. This flag is also being used to represent the owner of the tenant.
2. is_staff -> This user is used to represent the teacher.
3. Normal user -> These are the students on which is_superadmin and is_staff is False.

## Other Useful Info
- **Initial setup documentation [here](https://github.com/bernardopires/django-tenant-schemas#setup--documentation).**

- **Configure Tenant and Shared Applications -> [here](https://django-tenant-schemas.readthedocs.io/en/latest/install.html#configure-tenant-and-shared-applications)**


### Tenant
- Tenant application name - ```tenant```
- Tenant model - ```tenant/Tenant```

#### Tenant Default Admin on creation settings
- `TENANT_DEFAULT_SUPERUSER_USERNAME` - username of admin
- `TENANT_DEFAULT_SUPERUSER_PASSWORD` - password of admin


### Populating public schema and a admin user for public schema on first run
```shell
$ bash init_public_schema.sh
```


### Loading the dump
- place your dumps to the host location which can accessible by the `db` container (using volume mounts)

- create a tenant for the schema you want to dump, from admin

- ```$ docker exec db bash scripts/load_dump.sh <dump_location> <schema_name_to_dump_in>```

_Note: scheman_name_to_dump_in is same as tenant's name._

## Command line only Tasks

### Accessing the django shell

`docker-compose -f docker-compose.aws.yml -f docker-compose.prod.aws.yml exec web bash -c "./src/manage.py tenant_command shell"`


### Deleting a Tenant
For security purposes, and to prevent mistakes, deleting a tenant can only be done via command line


