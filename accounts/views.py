from datetime import date, timedelta
from decimal import Decimal

from django.contrib import messages
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import User
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import F
from django.shortcuts import get_object_or_404, redirect, render

from .forms import (
    PackingForm,
    PickingForm,
    PutawayForm,
    ReceivingForm,
    ShippingForm,
)
from .models import (
    Packing,
    Picking,
    Product,
    Putaway,
    Receiving,
    Shipping,
    WarehouseActivity, ProductLocation, ProductBatch, Order, OrderLine,
)


# =========================
# AUTHENTICATION
# =========================

def register_page(request):
    if request.user.is_authenticated:
        return redirect("dashboard")

    if request.method == "POST":
        username = request.POST.get("username", "").strip()
        email = request.POST.get("email", "").strip()
        password = request.POST.get("password", "")
        confirm_password = request.POST.get("confirm_password", "")

        if not username or not email or not password:
            messages.error(request, "Please fill in all required fields.")
        elif password != confirm_password:
            messages.error(request, "Passwords do not match.")
        elif len(password) < 8:
            messages.error(request, "Password must contain at least 8 characters.")
        elif User.objects.filter(username__iexact=username).exists():
            messages.error(request, "Username already exists.")
        elif User.objects.filter(email__iexact=email).exists():
            messages.error(request, "Email is already registered.")
        else:
            User.objects.create_user(
                username=username,
                email=email,
                password=password,
            )
            messages.success(request, "Account created successfully. Please log in.")
            return redirect("login")

    return render(request, "accounts/register.html")


def login_page(request):
    if request.user.is_authenticated:
        return redirect("dashboard")

    if request.method == "POST":
        username = request.POST.get("username", "").strip()
        password = request.POST.get("password", "")
        user = authenticate(request, username=username, password=password)

        if user is not None:
            profile = getattr(user, "staff_profile", None)
            if profile is not None and not profile.active:
                messages.error(request, "Your warehouse account is inactive. Contact an administrator.")
            else:
                login(request, user)
                return redirect(request.GET.get("next") or "dashboard")

        messages.error(request, "Invalid username or password.")

    return render(request, "accounts/index.html")


def logout_page(request):
    logout(request)
    messages.success(request, "You have been logged out.")
    return redirect("login")


# =========================
# DASHBOARD
# =========================

@login_required(login_url="login")
def dashboard(request):
    today = date.today()
    warning_date = today + timedelta(days=30)

    expiring_items = Receiving.objects.filter(
        expiry_date__isnull=False,
        quantity__gt=0,
    ).order_by("expiry_date")

    for item in expiring_items:
        if item.expiry_date <= today:
            item.row_class = "expired"
        elif item.expiry_date <= warning_date:
            item.row_class = "warning"
        else:
            item.row_class = "safe"

    context = {
        "products_count": Product.objects.count(),
        "receiving": Receiving.objects.count(),
        "putaway": Putaway.objects.count(),
        "inventory": Product.objects.count(),
        "picking": Picking.objects.count(),
        "packing": Packing.objects.count(),
        "shipping": Shipping.objects.count(),
        "activities": WarehouseActivity.objects.all().order_by("-created_at")[:15],
        "expiring_batches": expiring_items[:20],
        "today": today,
        "warning_date": warning_date,
    }
    return render(request, "accounts/dashboard.html", context)


# =========================
# PRODUCT / INVENTORY
# =========================

@login_required(login_url="login")
def inventory_page(request):
    products = Product.objects.all().order_by("name")
    query = request.GET.get("q", "").strip()
    if query:
        products = products.filter(Q(name__icontains=query) | Q(sku__icontains=query) | Q(barcode__icontains=query) | Q(category__icontains=query))
    low_stock = Product.objects.filter(quantity__lte=F("reorder_level")).order_by("quantity", "name")

    return render(
        request,
        "accounts/inventory.html",
        {"products": products, "low_stock": low_stock, "query": query},
    )


# =========================
# RECEIVING
# =========================

@login_required(login_url="login")
def receiving_page(request):
    form = ReceivingForm(request.POST or None)

    if request.method == "POST" and form.is_valid():
        with transaction.atomic():
            data = form.save()
            WarehouseActivity.objects.create(
                activity_type="RECEIVING",
                reference=f"RCV-{data.sku}",
                status="COMPLETED",
            )

        messages.success(request, "Goods received and inventory updated.")
        return redirect("receiving")

    records = Receiving.objects.all().order_by("-received_date")
    return render(
        request,
        "accounts/receiving.html",
        {"form": form, "records": records},
    )


# =========================
# PUTAWAY
# =========================

@login_required(login_url="login")
def putaway_page(request):
    form = PutawayForm(request.POST or None)

    if request.method == "POST" and form.is_valid():
        with transaction.atomic():
            receiving = Receiving.objects.select_for_update().get(
                pk=form.cleaned_data["receiving"].pk
            )
            if (
                receiving.status != "RECEIVED"
                or receiving.condition != Receiving.CONDITION_GOOD
            ):
                form.add_error(
                    "receiving",
                    "This receiving record is no longer available for putaway.",
                )
            else:
                putaway = form.save(commit=False)
                putaway.receiving = receiving
                putaway.status = "STORED"
                putaway.save()

                receiving.status = "STORED"
                receiving.save(update_fields=["status"])

                if not receiving.inventory_updated:
                    product, _ = Product.objects.get_or_create(
                        sku=receiving.sku,
                        defaults={"name": receiving.product_name, "quantity": 0},
                    )
                    product.name = receiving.product_name
                    product.quantity += receiving.quantity
                    product.save(update_fields=["name", "quantity"])
                    receiving.inventory_updated = True
                    receiving.save(update_fields=["inventory_updated"])

                product = Product.objects.get(sku=receiving.sku)
                if putaway.location_ref_id:
                    stock, _ = ProductLocation.objects.get_or_create(product=product, location=putaway.location_ref, defaults={"quantity": 0})
                    stock.quantity += receiving.quantity
                    stock.save(update_fields=["quantity", "updated_at"])

                if receiving.batch_number:
                    batch, created = ProductBatch.objects.get_or_create(product=product, batch_number=receiving.batch_number,
                        defaults={"quantity": receiving.quantity, "expiry_date": receiving.expiry_date})
                    if not created:
                        batch.quantity += receiving.quantity
                        if receiving.expiry_date and not batch.expiry_date:
                            batch.expiry_date = receiving.expiry_date
                        batch.save(update_fields=["quantity", "expiry_date"])

                WarehouseActivity.objects.create(
                    activity_type="PUTAWAY",
                    reference=f"PUT-{receiving.sku}",
                    status="COMPLETED",
                )
                messages.success(request, "Product stored and inventory updated.")
                return redirect("putaway")

    records = Putaway.objects.select_related("receiving").all().order_by("-created_at")
    return render(request, "accounts/putaway.html", {"form": form, "records": records})


# =========================
# PICKING
# =========================

@login_required(login_url="login")
def picking_page(request):
    form = PickingForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        quantity = form.cleaned_data["quantity"]
        selected_product = form.cleaned_data["product"]
        order_ref = form.cleaned_data["order_reference"].strip()
        with transaction.atomic():
            try:
                product = Product.objects.select_for_update().get(pk=selected_product.pk)
            except Product.DoesNotExist:
                form.add_error("product", "This inventory product is no longer available.")
            else:
                if product.quantity <= 0:
                    form.add_error("product", "This product is out of stock.")
                elif product.quantity < quantity:
                    form.add_error("quantity", f"Insufficient stock. Available quantity: {product.quantity}.")
                else:
                    order = Order.objects.filter(reference__iexact=order_ref).first()
                    ordered_qty = sum(OrderLine.objects.filter(order=order, product=product).values_list("quantity", flat=True)) if order else None
                    already_picked = sum(Picking.objects.filter(order_reference__iexact=order_ref, sku__iexact=product.sku).values_list("quantity", flat=True))
                    if order and order.status == "CANCELLED":
                        form.add_error("order_reference", "This order has been cancelled.")
                    elif order and ordered_qty == 0:
                        form.add_error("product", "This product is not listed on this order.")
                    elif order and already_picked + quantity > ordered_qty:
                        form.add_error("quantity", "Picking quantity exceeds the ordered quantity.")
                    else:
                        data = Picking.objects.create(product_name=product.name, sku=product.sku, quantity=quantity, order_reference=order_ref)
                        product.quantity -= quantity
                        product.save(update_fields=["quantity"])
                        WarehouseActivity.objects.create(activity_type="PICKING", reference=f"PICK-{data.order_reference}", status="COMPLETED")
                        _audit(request, "PICK", "Picking", data.order_reference, f"{product.sku} x {quantity}")
                        messages.success(request, f"Picking completed. {quantity} unit(s) reserved for order {data.order_reference}.")
                        return redirect("picking")
    records = Picking.objects.all().order_by("-created_at")
    return render(request, "accounts/picking.html", {"form": form, "records": records})


# =========================
# PACKING
# =========================

@login_required(login_url="login")
def packing_page(request):
    form = PackingForm(
        request.POST if request.method == "POST" else None,
        initial={"order_ref": request.GET.get("order_ref", "")},
    )

    if request.method == "POST" and form.is_valid():
        order_ref = form.cleaned_data["order_ref"].strip()
        product = form.cleaned_data["product"]
        quantity = form.cleaned_data["quantity"]

        picked_qty = sum(
            Picking.objects.filter(
                order_reference__iexact=order_ref,
                sku__iexact=product.sku,
            ).values_list("quantity", flat=True)
        )
        packed_qty = sum(
            Packing.objects.filter(
                order_ref__iexact=order_ref,
                product=product,
            ).values_list("quantity", flat=True)
        )

        if picked_qty == 0:
            form.add_error("order_ref", "No picking task exists for this order and product.")
        elif packed_qty + quantity > picked_qty:
            form.add_error(
                "quantity",
                f"Only {picked_qty - packed_qty} unit(s) remain to be packed for this order.",
            )
        else:
            data = form.save()
            WarehouseActivity.objects.create(
                activity_type="PACKING",
                reference=f"PK-{data.order_ref}",
                status="COMPLETED",
            )
            messages.success(request, "Packing completed successfully.")
            return redirect("packing")

    records = Packing.objects.select_related("product").all().order_by("-created_at")
    return render(request, "accounts/packing.html", {"form": form, "records": records})


# =========================
# SHIPPING
# =========================

@login_required(login_url="login")
def shipping_page(request):
    form = ShippingForm(
        request.POST if request.method == "POST" else None,
        initial={"order_ref": request.GET.get("order_ref", "")},
    )

    if request.method == "POST" and form.is_valid():
        order_ref = form.cleaned_data["order_ref"].strip()
        product = form.cleaned_data["product"]
        quantity = form.cleaned_data["quantity"]

        packed_qty = sum(
            Packing.objects.filter(
                order_ref__iexact=order_ref,
                product=product,
            ).values_list("quantity", flat=True)
        )
        shipped_qty = sum(
            Shipping.objects.filter(
                order_ref__iexact=order_ref,
                product=product,
            ).values_list("quantity", flat=True)
        )

        if packed_qty == 0:
            form.add_error("order_ref", "This order has not been packed yet.")
        elif shipped_qty + quantity > packed_qty:
            form.add_error(
                "quantity",
                f"Only {packed_qty - shipped_qty} packed unit(s) remain to ship.",
            )
        else:
            data = form.save()
            WarehouseActivity.objects.create(
                activity_type="SHIPPING",
                reference=f"SHP-{data.order_ref}",
                status="COMPLETED",
            )
            order = Order.objects.filter(reference__iexact=data.order_ref).first()
            if order and order.status != "CANCELLED":
                all_fulfilled = True
                any_shipped = False
                for line in order.lines.all():
                    shipped_for_line = sum(Shipping.objects.filter(order_ref__iexact=order.reference, product=line.product).values_list("quantity", flat=True))
                    any_shipped = any_shipped or shipped_for_line > 0
                    if shipped_for_line < line.quantity:
                        all_fulfilled = False
                order.status = "FULFILLED" if all_fulfilled and order.lines.exists() else ("PARTIALLY_FULFILLED" if any_shipped else "OPEN")
                order.save(update_fields=["status", "updated_at"])
            _audit(request, "SHIP", "Shipment", data.order_ref, f"{data.product.sku} x {data.quantity} to {data.destination}")
            messages.success(request, "Shipment created successfully.")
            return redirect("shipping")

    records = Shipping.objects.select_related("product").all().order_by("-shipped_at")
    return render(request, "accounts/shipping.html", {"form": form, "records": records})

# =========================
# MASTER DATA, STOCK CONTROL AND AUDIT (WMS UPDATE)
# =========================
from django.utils import timezone
from .forms import SupplierForm, CustomerForm, WarehouseLocationForm, StockAdjustmentForm
from .models import Supplier, Customer, WarehouseLocation, StockAdjustment, AuditLog, ProductLocation, StockTransfer


def _audit(request, action, object_type, reference="", details=""):
    AuditLog.objects.create(user=request.user if request.user.is_authenticated else None,
                            action=action, object_type=object_type,
                            object_reference=str(reference), details=details)

@login_required(login_url="login")
def suppliers_page(request):
    form = SupplierForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        obj = form.save()
        _audit(request, "CREATE", "Supplier", obj.code, f"Created supplier {obj.name}")
        messages.success(request, "Supplier saved successfully.")
        return redirect("suppliers")
    return render(request, "accounts/master_data.html", {"page_title": "Suppliers", "form": form, "records": Supplier.objects.all(), "columns": ["code", "name", "contact_person", "phone", "email"]})

@login_required(login_url="login")
def customers_page(request):
    form = CustomerForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        obj = form.save()
        _audit(request, "CREATE", "Customer", obj.code, f"Created customer {obj.name}")
        messages.success(request, "Customer saved successfully.")
        return redirect("customers")
    return render(request, "accounts/master_data.html", {"page_title": "Customers", "form": form, "records": Customer.objects.all(), "columns": ["code", "name", "contact_person", "phone", "email"]})

@login_required(login_url="login")
def locations_page(request):
    form = WarehouseLocationForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        obj = form.save()
        _audit(request, "CREATE", "Warehouse location", obj.pk, f"Created location {obj}")
        messages.success(request, "Warehouse location saved successfully.")
        return redirect("locations")
    return render(request, "accounts/master_data.html", {"page_title": "Warehouse Locations", "form": form, "records": WarehouseLocation.objects.all(), "columns": ["warehouse", "zone", "aisle", "rack", "bin", "is_active"]})

@login_required(login_url="login")
def adjustments_page(request):
    form = StockAdjustmentForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        obj = form.save(commit=False)
        obj.requested_by = request.user
        obj.save()
        _audit(request, "REQUEST", "Stock adjustment", obj.pk, f"{obj.product.sku}: {obj.change_quantity}; reason={obj.reason}")
        messages.success(request, "Adjustment submitted for staff approval. Inventory has not changed yet.")
        return redirect("adjustments")
    records = StockAdjustment.objects.select_related("product", "requested_by", "approved_by").all()
    return render(request, "accounts/adjustments.html", {"form": form, "records": records})

@login_required(login_url="login")
def review_adjustment(request, adjustment_id, decision):
    if not request.user.is_staff:
        messages.error(request, "Only warehouse managers or administrators can review adjustments.")
        return redirect("adjustments")
    if request.method != "POST":
        return redirect("adjustments")
    with transaction.atomic():
        obj = get_object_or_404(StockAdjustment.objects.select_for_update(), pk=adjustment_id)
        if obj.status != "PENDING":
            messages.warning(request, "This adjustment has already been reviewed.")
        elif decision == "approve":
            product = Product.objects.select_for_update().get(pk=obj.product_id)
            if product.quantity + obj.change_quantity < 0:
                messages.error(request, "Cannot approve: this would make inventory negative.")
            else:
                old_qty = product.quantity
                product.quantity += obj.change_quantity
                product.save(update_fields=["quantity"])
                obj.status = "APPROVED"
                obj.approved_by = request.user
                obj.reviewed_at = timezone.now()
                obj.save(update_fields=["status", "approved_by", "reviewed_at"])
                _audit(request, "APPROVE", "Stock adjustment", obj.pk, f"SKU {product.sku}: {old_qty} -> {product.quantity}; {obj.reason}")
                messages.success(request, "Adjustment approved and inventory updated.")
        elif decision == "reject":
            obj.status = "REJECTED"
            obj.approved_by = request.user
            obj.reviewed_at = timezone.now()
            obj.save(update_fields=["status", "approved_by", "reviewed_at"])
            _audit(request, "REJECT", "Stock adjustment", obj.pk, f"Rejected adjustment for {obj.product.sku}")
            messages.success(request, "Adjustment rejected.")
    return redirect("adjustments")

@login_required(login_url="login")
def reports_page(request):
    products = Product.objects.all().order_by("quantity", "name")
    context = {
        "products": products,
        "low_stock": Product.objects.filter(quantity__lte=F("reorder_level")).order_by("quantity", "name"),
        "adjustments_pending": StockAdjustment.objects.filter(status="PENDING").count(),
        "recent_audit": AuditLog.objects.select_related("user")[:30],
        "supplier_count": Supplier.objects.count(),
        "customer_count": Customer.objects.count(),
        "location_count": WarehouseLocation.objects.filter(is_active=True).count(),
    }
    return render(request, "accounts/reports.html", context)

# Additional operational workflows
from .models import Order, OrderLine, CycleCount, ReturnRecord, ProductBatch, StaffProfile
from .forms import StockTransferForm, OrderForm, OrderLineForm, CycleCountForm, ReturnRecordForm, ProductBatchForm
from django.db.models import Sum, Q
from django.http import HttpResponse
import csv


def _manager_required(request):
    return request.user.is_superuser or request.user.is_staff or (hasattr(request.user, 'staff_profile') and request.user.staff_profile.role in ['ADMIN','MANAGER'])

@login_required(login_url='login')
def transfers_page(request):
    form = StockTransferForm(request.POST or None)
    if request.method == 'POST' and form.is_valid():
        obj = form.save(commit=False)
        obj.requested_by = request.user
        obj.save()
        _audit(request, 'REQUEST', 'Stock transfer', obj.pk, f'{obj.product.sku}: {obj.quantity} from {obj.source} to {obj.destination}')
        messages.success(request, 'Transfer request created. A manager must complete it.')
        return redirect('transfers')
    return render(request, 'accounts/operations.html', {'title':'Stock Transfers','form':form,'records':StockTransfer.objects.select_related('product','source','destination','requested_by'),'kind':'transfers'})

@login_required(login_url='login')
def complete_transfer(request, transfer_id):
    if request.method != 'POST': return redirect('transfers')
    if not _manager_required(request):
        messages.error(request, 'Only managers or administrators can complete transfers.')
        return redirect('transfers')
    with transaction.atomic():
        transfer = get_object_or_404(StockTransfer.objects.select_for_update(), pk=transfer_id)
        if transfer.status != 'PENDING':
            messages.warning(request, 'This transfer is no longer pending.')
        else:
            source_stock = ProductLocation.objects.select_for_update().filter(product=transfer.product, location=transfer.source).first()
            if not source_stock or source_stock.quantity < transfer.quantity:
                messages.error(request, 'Insufficient stock at the source location. Record location stock before transferring.')
            else:
                source_stock.quantity -= transfer.quantity
                source_stock.save(update_fields=['quantity','updated_at'])
                target, _ = ProductLocation.objects.get_or_create(product=transfer.product, location=transfer.destination, defaults={'quantity':0})
                target.quantity += transfer.quantity
                target.save(update_fields=['quantity','updated_at'])
                transfer.status = 'COMPLETED'; transfer.completed_at = timezone.now()
                transfer.save(update_fields=['status','completed_at'])
                _audit(request, 'COMPLETE', 'Stock transfer', transfer.pk, f'{transfer.quantity} units moved from {transfer.source} to {transfer.destination}')
                messages.success(request, 'Transfer completed; source and destination balances updated.')
    return redirect('transfers')

@login_required(login_url='login')
def orders_page(request):
    form = OrderForm(request.POST or None)
    if request.method == 'POST' and form.is_valid():
        obj = form.save(commit=False); obj.created_by = request.user; obj.save()
        _audit(request, 'CREATE', 'Order', obj.reference, 'Order created')
        messages.success(request, 'Order created. Add its product lines below.')
        return redirect('order_detail', order_id=obj.pk)
    return render(request, 'accounts/operations.html', {'title':'Customer Orders','form':form,'records':Order.objects.select_related('customer','created_by').order_by('-created_at'),'kind':'orders'})

@login_required(login_url='login')
def order_detail(request, order_id):
    order = get_object_or_404(Order.objects.select_related('customer'), pk=order_id)
    form = OrderLineForm(request.POST or None)
    if request.method == 'POST' and form.is_valid():
        if order.status in ['FULFILLED','CANCELLED']:
            messages.error(request, 'Cannot add lines to a fulfilled or cancelled order.')
        else:
            line = form.save(commit=False); line.order = order; line.save()
            _audit(request, 'ADD_LINE', 'Order', order.reference, f'{line.product.sku} x {line.quantity}')
            messages.success(request, 'Order line added.')
        return redirect('order_detail', order_id=order.pk)
    return render(request, 'accounts/order_detail.html', {'order':order,'form':form,'lines':order.lines.select_related('product').all()})

@login_required(login_url='login')
def cancel_order(request, order_id):
    if request.method == 'POST':
        order = get_object_or_404(Order, pk=order_id)
        if not _manager_required(request): messages.error(request, 'Only managers can cancel orders.')
        elif order.status == 'FULFILLED': messages.error(request, 'Fulfilled orders cannot be cancelled.')
        else:
            order.status = 'CANCELLED'; order.save(update_fields=['status','updated_at'])
            _audit(request, 'CANCEL', 'Order', order.reference, 'Order cancelled')
            messages.success(request, 'Order cancelled.')
    return redirect('orders')

@login_required(login_url='login')
def cycle_counts_page(request):
    form = CycleCountForm(request.POST or None)
    if request.method == 'POST' and form.is_valid():
        obj = form.save(commit=False); obj.expected_quantity = obj.product.quantity; obj.counted_by = request.user; obj.save()
        _audit(request, 'COUNT', 'Cycle count', obj.pk, f'{obj.product.sku}: expected {obj.expected_quantity}, counted {obj.counted_quantity}')
        messages.success(request, 'Count saved. A manager must reconcile the variance.')
        return redirect('cycle_counts')
    records = CycleCount.objects.select_related('product','location','counted_by','reconciled_by').order_by('-created_at')
    return render(request, 'accounts/operations.html', {'title':'Cycle Counts','form':form,'records':records,'kind':'cycle_counts'})

@login_required(login_url='login')
def reconcile_count(request, count_id):
    if request.method != 'POST': return redirect('cycle_counts')
    if not _manager_required(request): messages.error(request, 'Only managers can reconcile counts.'); return redirect('cycle_counts')
    with transaction.atomic():
        count = get_object_or_404(CycleCount.objects.select_for_update(), pk=count_id)
        if count.status != 'OPEN': messages.warning(request, 'Count already reconciled or cancelled.')
        else:
            product = Product.objects.select_for_update().get(pk=count.product_id)
            old = product.quantity; delta = count.counted_quantity - count.expected_quantity
            product.quantity = max(0, old + delta); product.save(update_fields=['quantity'])
            if count.location_id:
                stock, _ = ProductLocation.objects.get_or_create(product=product, location=count.location, defaults={'quantity':0})
                stock.quantity = count.counted_quantity; stock.save(update_fields=['quantity','updated_at'])
            count.status='RECONCILED'; count.reconciled_by=request.user; count.reconciled_at=timezone.now(); count.save(update_fields=['status','reconciled_by','reconciled_at'])
            _audit(request,'RECONCILE','Cycle count',count.pk,f'{product.sku}: {old} -> {product.quantity}; delta {delta}')
            messages.success(request, 'Count reconciled and stock adjusted.')
    return redirect('cycle_counts')

@login_required(login_url='login')
def returns_page(request):
    form = ReturnRecordForm(request.POST or None)
    if request.method == 'POST' and form.is_valid():
        obj=form.save(commit=False); obj.created_by=request.user; obj.save()
        _audit(request,'CREATE','Return',obj.pk,f'{obj.return_type}: {obj.product.sku} x {obj.quantity}')
        messages.success(request,'Return recorded for inspection. Inventory has not changed yet.')
        return redirect('returns')
    records=ReturnRecord.objects.select_related('product','created_by','reviewed_by').order_by('-created_at')
    return render(request,'accounts/operations.html',{'title':'Returns and Quarantine','form':form,'records':records,'kind':'returns'})

@login_required(login_url='login')
def review_return(request, return_id, decision):
    if request.method != 'POST': return redirect('returns')
    if not _manager_required(request): messages.error(request,'Only managers can review returns.'); return redirect('returns')
    with transaction.atomic():
        obj=get_object_or_404(ReturnRecord.objects.select_for_update(),pk=return_id)
        if obj.status != 'PENDING': messages.warning(request,'This return has already been reviewed.')
        elif decision == 'restock' and obj.return_type == 'CUSTOMER' and obj.condition == 'GOOD':
            product=Product.objects.select_for_update().get(pk=obj.product_id); product.quantity += obj.quantity; product.save(update_fields=['quantity'])
            obj.status='RESTOCKED'; obj.reviewed_by=request.user; obj.reviewed_at=timezone.now(); obj.save(update_fields=['status','reviewed_by','reviewed_at'])
            _audit(request,'RESTOCK','Return',obj.pk,f'{product.sku} +{obj.quantity}'); messages.success(request,'Good returned stock added to inventory.')
        elif decision == 'quarantine':
            obj.status='QUARANTINED'; obj.reviewed_by=request.user; obj.reviewed_at=timezone.now(); obj.save(update_fields=['status','reviewed_by','reviewed_at'])
            _audit(request,'QUARANTINE','Return',obj.pk,'Return quarantined; not added to available stock'); messages.success(request,'Return quarantined and excluded from available stock.')
        elif decision == 'send' and obj.return_type == 'SUPPLIER':
            product=Product.objects.select_for_update().get(pk=obj.product_id)
            if product.quantity < obj.quantity: messages.error(request,'Cannot send return: available stock is insufficient.')
            else:
                product.quantity -= obj.quantity; product.save(update_fields=['quantity'])
                obj.status='SENT'; obj.reviewed_by=request.user; obj.reviewed_at=timezone.now(); obj.save(update_fields=['status','reviewed_by','reviewed_at'])
                _audit(request,'SUPPLIER_RETURN','Return',obj.pk,f'{product.sku} -{obj.quantity}'); messages.success(request,'Supplier return processed and stock reduced.')
        else:
            obj.status='REJECTED'; obj.reviewed_by=request.user; obj.reviewed_at=timezone.now(); obj.save(update_fields=['status','reviewed_by','reviewed_at'])
            _audit(request,'REJECT','Return',obj.pk,'Return rejected'); messages.success(request,'Return rejected.')
    return redirect('returns')

@login_required(login_url='login')
def batches_page(request):
    form=ProductBatchForm(request.POST or None)
    if request.method=='POST' and form.is_valid():
        obj=form.save(); _audit(request,'CREATE','Batch',obj.batch_number,f'{obj.product.sku}, qty {obj.quantity}, expiry {obj.expiry_date}')
        messages.success(request,'Batch saved. Batch quantities are tracked separately from total stock; update both through receiving/stock operations.')
        return redirect('batches')
    return render(request,'accounts/operations.html',{'title':'Batch and Expiry Tracking','form':form,'records':ProductBatch.objects.select_related('product').all(),'kind':'batches'})

@login_required(login_url='login')
def export_inventory(request):
    if not request.user.is_staff and not request.user.is_superuser:
        messages.error(request,'Only staff can export inventory.'); return redirect('inventory')
    response=HttpResponse(content_type='text/csv'); response['Content-Disposition']='attachment; filename="inventory.csv"'
    writer=csv.writer(response); writer.writerow(['SKU','Name','Barcode','Category','Quantity','UOM','Reorder level','Lead time days'])
    for p in Product.objects.all().order_by('sku'):
        writer.writerow([p.sku,p.name,p.barcode,p.category,p.quantity,p.unit_of_measure,p.reorder_level,p.lead_time_days])
    _audit(request,'EXPORT','Inventory','CSV','Inventory exported')
    return response

@login_required(login_url='login')
def staff_roles_page(request):
    if not _manager_required(request): messages.error(request,'Only managers can manage staff roles.'); return redirect('dashboard')
    if request.method=='POST':
        user=get_object_or_404(User,pk=request.POST.get('user_id'))
        role=request.POST.get('role')
        if role not in dict(StaffProfile.ROLES): messages.error(request,'Invalid role.')
        else:
            profile, _=StaffProfile.objects.get_or_create(user=user); profile.role=role; profile.active=request.POST.get('active')=='on'; profile.save()
            _audit(request,'ROLE_UPDATE','Staff',user.username,f'role={role}; active={profile.active}')
            messages.success(request,'Staff role updated.')
        return redirect('staff_roles')
    return render(request,'accounts/staff_roles.html',{'users':User.objects.all().order_by('username'),'roles':StaffProfile.ROLES})


@login_required(login_url="login")
def confirm_delivery(request, shipment_id):
    if request.method != "POST": return redirect("shipping")
    if not _manager_required(request):
        messages.error(request, "Only staff managers can confirm delivery.")
        return redirect("shipping")
    shipment = get_object_or_404(Shipping, pk=shipment_id)
    if shipment.status == "DELIVERED":
        messages.info(request, "Delivery has already been confirmed.")
    else:
        shipment.status = "DELIVERED"
        shipment.delivered_at = timezone.now()
        shipment.proof_of_delivery = request.POST.get("proof_of_delivery", "").strip()
        shipment.save(update_fields=["status", "delivered_at", "proof_of_delivery"])
        _audit(request, "DELIVERY_CONFIRMED", "Shipment", shipment.order_ref, f"Tracking {shipment.tracking_number}; proof recorded")
        messages.success(request, "Delivery confirmed and proof of delivery saved.")
    return redirect("shipping")


@login_required(login_url="login")
def import_inventory(request):
    if not request.user.is_staff and not request.user.is_superuser:
        messages.error(request, "Only staff can import inventory.")
        return redirect("inventory")
    if request.method == "POST":
        uploaded = request.FILES.get("file")
        if not uploaded or not uploaded.name.lower().endswith(".csv"):
            messages.error(request, "Choose a CSV file. Required columns: sku,name,quantity.")
            return redirect("inventory")
        try:
            decoded = uploaded.read().decode("utf-8-sig")
            reader = csv.DictReader(decoded.splitlines())
            required = {"sku", "name", "quantity"}
            if not reader.fieldnames or not required.issubset({h.strip().lower() for h in reader.fieldnames}):
                raise ValueError("CSV must include sku, name and quantity columns.")
            count = 0
            with transaction.atomic():
                for row in reader:
                    row = {str(k).strip().lower(): (v or "").strip() for k, v in row.items() if k is not None}
                    sku = row.get("sku", "")
                    name = row.get("name", "")
                    quantity = int(row.get("quantity", "0"))
                    if not sku or not name or quantity < 0:
                        raise ValueError("Each row needs SKU/name and a non-negative quantity.")
                    defaults = {"name": name, "quantity": quantity, "barcode": row.get("barcode", ""), "category": row.get("category", ""), "unit_of_measure": row.get("unit_of_measure", "piece") or "piece", "reorder_level": int(row.get("reorder_level", "5") or 5), "lead_time_days": int(row.get("lead_time_days", "0") or 0)}
                    Product.objects.update_or_create(sku=sku, defaults=defaults)
                    count += 1
            _audit(request, "IMPORT", "Inventory", "CSV", f"Imported/updated {count} products")
            messages.success(request, f"Imported or updated {count} products.")
        except (UnicodeDecodeError, csv.Error, ValueError, TypeError) as exc:
            messages.error(request, f"Import failed; no rows were saved. Check the CSV: {exc}")
        return redirect("inventory")
    return redirect("inventory")
