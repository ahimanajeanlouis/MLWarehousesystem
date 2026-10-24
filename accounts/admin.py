from django.contrib import admin
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
