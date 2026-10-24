from django.contrib import admin

from .models import (
    AuditLog,
    Customer,
    CycleCount,
    Order,
    OrderLine,
    Packing,
    Picking,
    Product,
    ProductBatch,
    ProductLocation,
    Putaway,
    Receiving,
    ReturnRecord,
    Shipping,
    StaffProfile,
    StockAdjustment,
    StockTransfer,
    Supplier,
    WarehouseActivity,
    WarehouseLocation,
)


@admin.register(StaffProfile)
class StaffProfileAdmin(admin.ModelAdmin):
    list_display = ("user", "role", "active")
    list_filter = ("role", "active")
    search_fields = ("user__username", "user__email")


@admin.register(Product)
class ProductAdmin(admin.ModelAdmin):
    list_display = ("sku", "name", "quantity", "category", "reorder_level", "barcode")
    search_fields = ("sku", "name", "barcode")
    list_filter = ("category",)


@admin.register(Receiving)
class ReceivingAdmin(admin.ModelAdmin):
    list_display = ("sku", "product_name", "quantity", "supplier", "condition", "status", "received_date")
    search_fields = ("sku", "product_name", "supplier", "batch_number")
    list_filter = ("condition", "status")


admin.site.register([
    AuditLog,
    Customer,
    CycleCount,
    Order,
    OrderLine,
    Packing,
    Picking,
    ProductBatch,
    ProductLocation,
    Putaway,
    ReturnRecord,
    Shipping,
    StockAdjustment,
    StockTransfer,
    Supplier,
    WarehouseActivity,
    WarehouseLocation,
])