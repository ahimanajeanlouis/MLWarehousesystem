from django.urls import path
from . import views

urlpatterns = [
    path("", views.login_page, name="login"),
    path("register/", views.register_page, name="register"),
    path("dashboard/", views.dashboard, name="dashboard"),
    path("logout/", views.logout_page, name="logout"),
    path("receiving/", views.receiving_page, name="receiving"),
    path("putaway/", views.putaway_page, name="putaway"),
    path("inventory/", views.inventory_page, name="inventory"),
    path("picking/", views.picking_page, name="picking"),
    path("packing/", views.packing_page, name="packing"),
    path("shipping/", views.shipping_page, name="shipping"),
<<<<<<< HEAD
=======
    path("suppliers/", views.suppliers_page, name="suppliers"),
    path("customers/", views.customers_page, name="customers"),
    path("locations/", views.locations_page, name="locations"),
    path("adjustments/", views.adjustments_page, name="adjustments"),
    path("adjustments/<int:adjustment_id>/<str:decision>/", views.review_adjustment, name="review_adjustment"),
    path("reports/", views.reports_page, name="reports"),
    path('transfers/', views.transfers_page, name='transfers'),
    path('transfers/<int:transfer_id>/complete/', views.complete_transfer, name='complete_transfer'),
    path('orders/', views.orders_page, name='orders'),
    path('orders/<int:order_id>/', views.order_detail, name='order_detail'),
    path('orders/<int:order_id>/cancel/', views.cancel_order, name='cancel_order'),
    path('cycle-counts/', views.cycle_counts_page, name='cycle_counts'),
    path('cycle-counts/<int:count_id>/reconcile/', views.reconcile_count, name='reconcile_count'),
    path('returns/', views.returns_page, name='returns'),
    path('returns/<int:return_id>/<str:decision>/', views.review_return, name='review_return'),
    path('batches/', views.batches_page, name='batches'),
    path('inventory/export/', views.export_inventory, name='export_inventory'),
    path('inventory/import/', views.import_inventory, name='import_inventory'),
    path('staff-roles/', views.staff_roles_page, name='staff_roles'),
    path('shipping/<int:shipment_id>/delivered/', views.confirm_delivery, name='confirm_delivery'),
>>>>>>> origin/main
]
