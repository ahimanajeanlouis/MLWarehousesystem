from django.contrib import admin
from .models import Product, UserRole, WarehouseActivity, Receiving, Putaway, Picking, Packing, Shipping

@admin.register(UserRole)
class UserRoleAdmin(admin.ModelAdmin):
	list_display = ("user", "role")
	list_filter = ("role",)
	search_fields = ("user__username", "user__email")


admin.site.register(Product)
admin.site.register(WarehouseActivity)
admin.site.register(Receiving)
admin.site.register(Putaway)
admin.site.register(Picking)
admin.site.register(Packing)
admin.site.register(Shipping)
