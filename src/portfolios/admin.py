from django.contrib import admin

# from portfolios.models import Portfolio
from tenant.admin import NonPublicSchemaOnlyAdminAccessMixin


class PortfolioAdmin(NonPublicSchemaOnlyAdminAccessMixin, admin.ModelAdmin):
    pass


# admin.site.register(Portfolio, PortfolioAdmin)
