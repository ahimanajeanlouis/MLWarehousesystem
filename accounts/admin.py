from django.contrib import admin

from .models import (
    AuditLog, Customer, CycleCount, Order, OrderLine, Packing, Picking, Product,
    ProductBatch, ProductLocation, Putaway, Receiving, ReturnRecord, Shipping,
    StaffProfile, StaffRole, StockAdjustment, StockTransfer, Supplier,
    WarehouseActivity, WarehouseLocation,
)


@admin.register(StaffRole)
class StaffRoleAdmin(admin.ModelAdmin):
    list_display = ("code", "name")
    search_fields = ("code", "name")


@admin.register(StaffProfile)
class StaffProfileAdmin(admin.ModelAdmin):
    filter_horizontal = ("roles",)
    list_display = ("user", "active")
    list_filter = ("roles", "active")
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
    AuditLog, Customer, CycleCount, Order, OrderLine, Packing, Picking,
    ProductBatch, ProductLocation, Putaway, ReturnRecord, Shipping,
    StockAdjustment, StockTransfer, Supplier, WarehouseActivity, WarehouseLocation,
])
