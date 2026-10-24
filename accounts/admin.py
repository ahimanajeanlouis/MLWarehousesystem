from django.contrib import admin
<<<<<<< HEAD
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
=======
from .models import (
    Product, WarehouseActivity, Receiving, Putaway, Picking, Packing, Shipping,
    Supplier, Customer, WarehouseLocation, ProductLocation, StockAdjustment,
    AuditLog, StockTransfer, Order, OrderLine, CycleCount, ReturnRecord,
    ProductBatch, StaffProfile,
)

@admin.register(Product)
class ProductAdmin(admin.ModelAdmin):
    list_display = ('sku','name','quantity','category','reorder_level','barcode')
    search_fields = ('sku','name','barcode')
    list_filter = ('category',)

@admin.register(Receiving)
class ReceivingAdmin(admin.ModelAdmin):
    list_display = ('sku','product_name','quantity','supplier','condition','status','received_date')
    search_fields = ('sku','product_name','supplier','batch_number')
    list_filter = ('condition','status')

for model in [WarehouseActivity, Putaway, Picking, Packing, Shipping, Supplier, Customer,
              WarehouseLocation, ProductLocation, StockAdjustment, AuditLog, StockTransfer,
              Order, OrderLine, CycleCount, ReturnRecord, ProductBatch, StaffProfile]:
    try: admin.site.register(model)
    except admin.sites.AlreadyRegistered: pass
>>>>>>> origin/main
