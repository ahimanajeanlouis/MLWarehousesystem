import csv
from datetime import date, timedelta
from decimal import Decimal
from html import escape
from io import BytesIO

from django.contrib import messages
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import User
from django.db import transaction
from django.db.models import F, Q
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from .forms import (
    CustomerForm, CycleCountForm, OrderForm, OrderLineForm, PackingForm,
    PickingForm, ProductBatchForm, PutawayForm, ReceivingForm, ReturnRecordForm,
    ShippingForm, StockAdjustmentForm, StockTransferForm, SupplierForm,
    WarehouseLocationForm,
)
from .models import (
    AuditLog, Customer, CycleCount, Order, OrderLine, Packing, Picking,
    Product, ProductBatch, ProductLocation, Putaway, Receiving, ReturnRecord,
    Shipping, StaffProfile, StaffRole, StockAdjustment, StockTransfer, Supplier,
    WarehouseActivity, WarehouseLocation,
)
from .permissions import module_required, modules_for_user


def _audit(request, action, object_type, reference="", details=""):
    AuditLog.objects.create(
        user=request.user if request.user.is_authenticated else None,
        action=action, object_type=object_type,
        object_reference=str(reference), details=details,
    )


def _manager_required(request):
    user = request.user
    if user.is_superuser or user.is_staff:
        return True
    profile = getattr(user, "staff_profile", None)
    return bool(profile and profile.active and profile.roles.filter(code__in=("ADMIN", "MANAGER")).exists())


def register_page(request):
    # Employee creation is restricted to managers; there is no public signup.
    if not request.user.is_authenticated:
        return redirect("login")
    if not _manager_required(request):
        return HttpResponse("Only administrators and managers can create employees.", status=403)
    if request.method == "POST":
        username = request.POST.get("username", "").strip()
        email = request.POST.get("email", "").strip()
        password = request.POST.get("password", "")
        confirm = request.POST.get("confirm_password", "")
        if not username or not email or not password:
            messages.error(request, "Please fill in all required fields.")
        elif password != confirm:
            messages.error(request, "Passwords do not match.")
        elif len(password) < 8:
            messages.error(request, "Password must contain at least 8 characters.")
        elif User.objects.filter(username__iexact=username).exists():
            messages.error(request, "Username already exists.")
        elif User.objects.filter(email__iexact=email).exists():
            messages.error(request, "Email is already registered.")
        else:
            with transaction.atomic():
                user = User.objects.create_user(username=username, email=email, password=password)
                StaffProfile.objects.create(user=user)
            messages.success(request, "Employee account created. Assign roles below.")
            return redirect("staff_roles")
    return render(request, "accounts/register.html")


def login_page(request):
    if request.user.is_authenticated:
        return redirect("dashboard")
    if request.method == "POST":
        user = authenticate(
            request, username=request.POST.get("username", "").strip(),
            password=request.POST.get("password", ""),
        )
        if user:
            profile = getattr(user, "staff_profile", None)
            if profile and not profile.active:
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


@login_required(login_url="login")
@module_required("dashboard")
def dashboard(request):
    today = timezone.localdate()
    warning_date = today + timedelta(days=30)
    expiring = Receiving.objects.filter(expiry_date__isnull=False, quantity__gt=0).order_by("expiry_date")
    for item in expiring:
        item.row_class = "expired" if item.expiry_date <= today else ("warning" if item.expiry_date <= warning_date else "safe")
    modules = modules_for_user(request.user)
    context = {
        "products_count": Product.objects.count(), "receiving": Receiving.objects.count(),
        "putaway": Putaway.objects.count(), "inventory": Product.objects.count(),
        "picking": Picking.objects.count(), "packing": Packing.objects.count(),
        "shipping": Shipping.objects.count(),
        "activities": WarehouseActivity.objects.filter(
            activity_type__in=[m.upper() for m in modules if m != "dashboard"]
        ).order_by("-created_at")[:15],
        "expiring_batches": expiring[:20] if "receiving" in modules else [],
        "dashboard_modules": modules, "today": today, "warning_date": warning_date,
    }
    return render(request, "accounts/dashboard.html", context)


@login_required(login_url="login")
@module_required("dashboard")
def download_report(request):
    modules = modules_for_user(request.user)
    period = request.GET.get("period", "")
    today = timezone.localdate()
    if period == "daily":
        start = end = today
        label = "Daily"
    elif period == "weekly":
        start = today - timedelta(days=today.weekday())
        end = start + timedelta(days=6)
        label = "Weekly"
    elif period == "monthly":
        start = date(today.year, today.month, 1)
        end = (date(today.year + (today.month == 12), today.month % 12 + 1, 1) - timedelta(days=1))
        label = "Monthly"
    else:
        return HttpResponse("Choose a valid report period.", status=400)
    buffer = BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=landscape(A4), rightMargin=28, leftMargin=28, topMargin=28, bottomMargin=28)
    styles = getSampleStyleSheet()
    cell = ParagraphStyle("ReportCell", parent=styles["BodyText"], fontSize=8, leading=10)
    story = [Paragraph(f"{label} Warehouse Operations Report", styles["Title"]),
             Paragraph(f"User: {escape(request.user.username)}", styles["Normal"]),
             Paragraph(f"Report period: {start:%Y-%m-%d} to {end:%Y-%m-%d}", styles["Normal"]),
             Paragraph(f"Generated: {timezone.localtime():%Y-%m-%d %H:%M}", styles["Normal"]), Spacer(1, 12)]

    def add_section(title, headers, rows):
        story.append(Paragraph(escape(title), styles["Heading2"]))
        if not rows:
            story.append(Paragraph("No records available.", styles["Normal"]))
            return
        data = [[Paragraph(escape(str(x)), cell) for x in headers]]
        data += [[Paragraph(escape(str(x)), cell) for x in row] for row in rows]
        table = Table(data, colWidths=[786 / len(headers)] * len(headers), repeatRows=1)
        table.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#24445c")),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
            ("GRID", (0, 0), (-1, -1), .35, colors.HexColor("#b7c2ca")),
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f1f5f7")]),
        ]))
        story.extend([table, Spacer(1, 12)])

    if "receiving" in modules:
        rows = Receiving.objects.filter(received_date__date__range=(start, end)).order_by("-received_date")
        add_section("Receiving", ["Product", "SKU", "Quantity", "Status", "Received"], [(x.product_name, x.sku, x.quantity, x.status, x.received_date.date()) for x in rows])
    if "putaway" in modules:
        rows = Putaway.objects.filter(created_at__date__range=(start, end)).select_related("receiving").order_by("-created_at")
        add_section("Putaway", ["SKU", "Product", "Location", "Status", "Created"], [(x.receiving.sku, x.receiving.product_name, x.location, x.status, x.created_at.date()) for x in rows])
    if "inventory" in modules:
        add_section("Inventory", ["SKU", "Product", "Quantity", "Category", "Reorder level"], [(x.sku, x.name, x.quantity, x.category, x.reorder_level) for x in Product.objects.order_by("name")])
    for module, model, date_field, title, headers, values in (
        ("picking", Picking, "created_at", "Picking", ["Order", "Product", "SKU", "Quantity", "Status"], lambda x: (x.order_reference, x.product_name, x.sku, x.quantity, x.status)),
        ("packing", Packing, "created_at", "Packing", ["Order", "Product", "SKU", "Quantity", "Status"], lambda x: (x.order_ref, x.product.name, x.product.sku, x.quantity, x.status)),
        ("shipping", Shipping, "shipped_at", "Shipping", ["Order", "Product", "SKU", "Quantity", "Destination", "Status"], lambda x: (x.order_ref, x.product.name, x.product.sku, x.quantity, x.destination, x.status)),
    ):
        if module in modules:
            rows = model.objects.filter(**{f"{date_field}__date__range": (start, end)}).select_related("product").order_by(f"-{date_field}")
            add_section(title, headers, [values(x) for x in rows])
    doc.build(story)
    response = HttpResponse(buffer.getvalue(), content_type="application/pdf")
    response["Content-Disposition"] = f'attachment; filename="warehouse-report-{period}-{request.user.username}.pdf"'
    return response


@login_required(login_url="login")
@module_required("inventory")
def inventory_page(request):
    query = request.GET.get("q", "").strip()
    products = Product.objects.all().order_by("name")
    if query:
        products = products.filter(Q(name__icontains=query) | Q(sku__icontains=query) | Q(barcode__icontains=query) | Q(category__icontains=query))
    low_stock = Product.objects.filter(quantity__lte=F("reorder_level")).order_by("quantity", "name")
    return render(request, "accounts/inventory.html", {"products": products, "low_stock": low_stock, "query": query})


@login_required(login_url="login")
@module_required("receiving")
def receiving_page(request):
    form = ReceivingForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        with transaction.atomic():
            obj = form.save()
            WarehouseActivity.objects.create(activity_type="RECEIVING", reference=f"RCV-{obj.sku}", status="COMPLETED")
        messages.success(request, "Goods received successfully.")
        return redirect("receiving")
    return render(request, "accounts/receiving.html", {"form": form, "records": Receiving.objects.all().order_by("-received_date")})


@login_required(login_url="login")
@module_required("putaway")
def putaway_page(request):
    form = PutawayForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        with transaction.atomic():
            receiving = Receiving.objects.select_for_update().get(pk=form.cleaned_data["receiving"].pk)
            if receiving.status != "RECEIVED" or receiving.condition != Receiving.CONDITION_GOOD:
                form.add_error("receiving", "This receiving record is no longer available for putaway.")
            else:
                obj = form.save(commit=False)
                obj.receiving, obj.status = receiving, "STORED"
                obj.save()
                receiving.status = "STORED"
                receiving.save(update_fields=["status"])
                product, _ = Product.objects.get_or_create(sku=receiving.sku, defaults={"name": receiving.product_name, "quantity": 0})
                product.name = receiving.product_name
                if not receiving.inventory_updated:
                    product.quantity += receiving.quantity
                    receiving.inventory_updated = True
                    receiving.save(update_fields=["inventory_updated"])
                product.save(update_fields=["name", "quantity"])
                if obj.location_ref_id:
                    stock, _ = ProductLocation.objects.get_or_create(product=product, location=obj.location_ref, defaults={"quantity": 0})
                    stock.quantity += receiving.quantity
                    stock.save(update_fields=["quantity", "updated_at"])
                if receiving.batch_number:
                    batch, created = ProductBatch.objects.get_or_create(product=product, batch_number=receiving.batch_number, defaults={"quantity": receiving.quantity, "expiry_date": receiving.expiry_date})
                    if not created:
                        batch.quantity += receiving.quantity
                        if receiving.expiry_date and not batch.expiry_date:
                            batch.expiry_date = receiving.expiry_date
                        batch.save(update_fields=["quantity", "expiry_date"])
                WarehouseActivity.objects.create(activity_type="PUTAWAY", reference=f"PUT-{receiving.sku}", status="COMPLETED")
                messages.success(request, "Product stored and inventory updated.")
                return redirect("putaway")
    records = Putaway.objects.select_related("receiving").order_by("-created_at")
    return render(request, "accounts/putaway.html", {"form": form, "records": records})


@login_required(login_url="login")
@module_required("picking")
def picking_page(request):
    form = PickingForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        quantity, selected = form.cleaned_data["quantity"], form.cleaned_data["product"]
        order_ref = form.cleaned_data["order_reference"].strip()
        with transaction.atomic():
            product = Product.objects.select_for_update().get(pk=selected.pk)
            order = Order.objects.filter(reference__iexact=order_ref).first()
            ordered = sum(OrderLine.objects.filter(order=order, product=product).values_list("quantity", flat=True)) if order else None
            picked = sum(Picking.objects.filter(order_reference__iexact=order_ref, sku__iexact=product.sku).values_list("quantity", flat=True))
            if product.quantity < quantity:
                form.add_error("quantity", f"Insufficient stock. Available quantity: {product.quantity}.")
            elif order and order.status == "CANCELLED":
                form.add_error("order_reference", "This order has been cancelled.")
            elif order and ordered == 0:
                form.add_error("product", "This product is not listed on this order.")
            elif order and picked + quantity > ordered:
                form.add_error("quantity", "Picking quantity exceeds the ordered quantity.")
            else:
                obj = Picking.objects.create(product_name=product.name, sku=product.sku, quantity=quantity, order_reference=order_ref)
                product.quantity -= quantity
                product.save(update_fields=["quantity"])
                WarehouseActivity.objects.create(activity_type="PICKING", reference=f"PICK-{obj.order_reference}", status="COMPLETED")
                _audit(request, "PICK", "Picking", obj.order_reference, f"{product.sku} x {quantity}")
                messages.success(request, f"Picking completed for {order_ref}.")
                return redirect("picking")
    return render(request, "accounts/picking.html", {"form": form, "records": Picking.objects.all().order_by("-created_at")})


@login_required(login_url="login")
@module_required("packing")
def packing_page(request):
    form = PackingForm(request.POST if request.method == "POST" else None, initial={"order_ref": request.GET.get("order_ref", "")})
    if request.method == "POST" and form.is_valid():
        order_ref, product, quantity = form.cleaned_data["order_ref"].strip(), form.cleaned_data["product"], form.cleaned_data["quantity"]
        picked = sum(Picking.objects.filter(order_reference__iexact=order_ref, sku__iexact=product.sku).values_list("quantity", flat=True))
        packed = sum(Packing.objects.filter(order_ref__iexact=order_ref, product=product).values_list("quantity", flat=True))
        if picked == 0:
            form.add_error("order_ref", "No picking task exists for this order and product.")
        elif packed + quantity > picked:
            form.add_error("quantity", f"Only {picked - packed} unit(s) remain to be packed.")
        else:
            obj = form.save()
            WarehouseActivity.objects.create(activity_type="PACKING", reference=f"PK-{obj.order_ref}", status="COMPLETED")
            messages.success(request, "Packing completed successfully.")
            return redirect("packing")
    return render(request, "accounts/packing.html", {"form": form, "records": Packing.objects.select_related("product").order_by("-created_at")})


@login_required(login_url="login")
@module_required("shipping")
def shipping_page(request):
    form = ShippingForm(request.POST if request.method == "POST" else None, initial={"order_ref": request.GET.get("order_ref", "")})
    if request.method == "POST" and form.is_valid():
        order_ref, product, quantity = form.cleaned_data["order_ref"].strip(), form.cleaned_data["product"], form.cleaned_data["quantity"]
        packed = sum(Packing.objects.filter(order_ref__iexact=order_ref, product=product).values_list("quantity", flat=True))
        shipped = sum(Shipping.objects.filter(order_ref__iexact=order_ref, product=product).values_list("quantity", flat=True))
        if packed == 0:
            form.add_error("order_ref", "This order has not been packed yet.")
        elif shipped + quantity > packed:
            form.add_error("quantity", f"Only {packed - shipped} packed unit(s) remain to ship.")
        else:
            obj = form.save()
            WarehouseActivity.objects.create(activity_type="SHIPPING", reference=f"SHP-{obj.order_ref}", status="COMPLETED")
            order = Order.objects.filter(reference__iexact=obj.order_ref).first()
            if order and order.status != "CANCELLED":
                done = all(sum(Shipping.objects.filter(order_ref__iexact=order.reference, product=line.product).values_list("quantity", flat=True)) >= line.quantity for line in order.lines.all())
                any_shipped = Shipping.objects.filter(order_ref__iexact=order.reference).exists()
                order.status = "FULFILLED" if done and order.lines.exists() else ("PARTIALLY_FULFILLED" if any_shipped else "OPEN")
                order.save(update_fields=["status", "updated_at"])
            _audit(request, "SHIP", "Shipment", obj.order_ref, f"{obj.product.sku} x {obj.quantity}")
            messages.success(request, "Shipment created successfully.")
            return redirect("shipping")
    return render(request, "accounts/shipping.html", {"form": form, "records": Shipping.objects.select_related("product").order_by("-shipped_at")})


@login_required(login_url="login")
@module_required("management")
def suppliers_page(request):
    form = SupplierForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        obj = form.save(); _audit(request, "CREATE", "Supplier", obj.code, obj.name); messages.success(request, "Supplier saved successfully."); return redirect("suppliers")
    return render(request, "accounts/master_data.html", {"page_title": "Suppliers", "form": form, "records": Supplier.objects.all(), "columns": ["code", "name", "contact_person", "phone", "email"]})


@login_required(login_url="login")
@module_required("management")
def customers_page(request):
    form = CustomerForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        obj = form.save(); _audit(request, "CREATE", "Customer", obj.code, obj.name); messages.success(request, "Customer saved successfully."); return redirect("customers")
    return render(request, "accounts/master_data.html", {"page_title": "Customers", "form": form, "records": Customer.objects.all(), "columns": ["code", "name", "contact_person", "phone", "email"]})


@login_required(login_url="login")
@module_required("management")
def locations_page(request):
    form = WarehouseLocationForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        obj = form.save(); _audit(request, "CREATE", "Warehouse location", obj.pk, str(obj)); messages.success(request, "Warehouse location saved successfully."); return redirect("locations")
    return render(request, "accounts/master_data.html", {"page_title": "Warehouse Locations", "form": form, "records": WarehouseLocation.objects.all(), "columns": ["warehouse", "zone", "aisle", "rack", "bin", "is_active"]})


@login_required(login_url="login")
@module_required("management")
def adjustments_page(request):
    form = StockAdjustmentForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        obj = form.save(commit=False); obj.requested_by = request.user; obj.save(); _audit(request, "REQUEST", "Stock adjustment", obj.pk, f"{obj.product.sku}: {obj.change_quantity}"); messages.success(request, "Adjustment submitted for approval."); return redirect("adjustments")
    records = StockAdjustment.objects.select_related("product", "requested_by", "approved_by")
    return render(request, "accounts/adjustments.html", {"form": form, "records": records})


@login_required(login_url="login")
@module_required("management")
def review_adjustment(request, adjustment_id, decision):
    if request.method != "POST": return redirect("adjustments")
    if not _manager_required(request): messages.error(request, "Only managers can review adjustments."); return redirect("adjustments")
    with transaction.atomic():
        obj = get_object_or_404(StockAdjustment.objects.select_for_update(), pk=adjustment_id)
        if obj.status != "PENDING": messages.warning(request, "This adjustment has already been reviewed.")
        elif decision == "approve":
            product = Product.objects.select_for_update().get(pk=obj.product_id)
            if product.quantity + obj.change_quantity < 0: messages.error(request, "This adjustment would make inventory negative.")
            else:
                product.quantity += obj.change_quantity; product.save(update_fields=["quantity"])
                obj.status, obj.approved_by, obj.reviewed_at = "APPROVED", request.user, timezone.now(); obj.save(update_fields=["status", "approved_by", "reviewed_at"])
                _audit(request, "APPROVE", "Stock adjustment", obj.pk, product.sku); messages.success(request, "Adjustment approved.")
        elif decision == "reject":
            obj.status, obj.approved_by, obj.reviewed_at = "REJECTED", request.user, timezone.now(); obj.save(update_fields=["status", "approved_by", "reviewed_at"]); messages.success(request, "Adjustment rejected.")
    return redirect("adjustments")


@login_required(login_url="login")
@module_required("management")
def reports_page(request):
    return render(request, "accounts/reports.html", {
        "products": Product.objects.order_by("quantity", "name"),
        "low_stock": Product.objects.filter(quantity__lte=F("reorder_level")).order_by("quantity", "name"),
        "adjustments_pending": StockAdjustment.objects.filter(status="PENDING").count(),
        "recent_audit": AuditLog.objects.select_related("user")[:30],
        "supplier_count": Supplier.objects.count(), "customer_count": Customer.objects.count(),
        "location_count": WarehouseLocation.objects.filter(is_active=True).count(),
    })


@login_required(login_url="login")
@module_required("management")
def transfers_page(request):
    form = StockTransferForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        obj = form.save(commit=False); obj.requested_by = request.user; obj.save(); _audit(request, "REQUEST", "Stock transfer", obj.pk, obj.product.sku); messages.success(request, "Transfer request created."); return redirect("transfers")
    return render(request, "accounts/operations.html", {"title": "Stock Transfers", "form": form, "records": StockTransfer.objects.select_related("product", "source", "destination", "requested_by"), "kind": "transfers"})


@login_required(login_url="login")
@module_required("management")
def complete_transfer(request, transfer_id):
    if request.method != "POST": return redirect("transfers")
    if not _manager_required(request): messages.error(request, "Only managers can complete transfers."); return redirect("transfers")
    with transaction.atomic():
        transfer = get_object_or_404(StockTransfer.objects.select_for_update(), pk=transfer_id)
        source = ProductLocation.objects.select_for_update().filter(product=transfer.product, location=transfer.source).first()
        if transfer.status != "PENDING": messages.warning(request, "This transfer is no longer pending.")
        elif not source or source.quantity < transfer.quantity: messages.error(request, "Insufficient stock at source location.")
        else:
            source.quantity -= transfer.quantity; source.save(update_fields=["quantity", "updated_at"])
            target, _ = ProductLocation.objects.get_or_create(product=transfer.product, location=transfer.destination, defaults={"quantity": 0})
            target.quantity += transfer.quantity; target.save(update_fields=["quantity", "updated_at"])
            transfer.status, transfer.completed_at = "COMPLETED", timezone.now(); transfer.save(update_fields=["status", "completed_at"])
            _audit(request, "COMPLETE", "Stock transfer", transfer.pk, str(transfer.quantity)); messages.success(request, "Transfer completed.")
    return redirect("transfers")


@login_required(login_url="login")
@module_required("management")
def orders_page(request):
    form = OrderForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        obj = form.save(commit=False); obj.created_by = request.user; obj.save(); _audit(request, "CREATE", "Order", obj.reference); messages.success(request, "Order created. Add product lines."); return redirect("order_detail", order_id=obj.pk)
    return render(request, "accounts/operations.html", {"title": "Customer Orders", "form": form, "records": Order.objects.select_related("customer", "created_by").order_by("-created_at"), "kind": "orders"})


@login_required(login_url="login")
@module_required("management")
def order_detail(request, order_id):
    order = get_object_or_404(Order.objects.select_related("customer"), pk=order_id)
    form = OrderLineForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        if order.status in ("FULFILLED", "CANCELLED"): messages.error(request, "Cannot add lines to a fulfilled or cancelled order.")
        else:
            line = form.save(commit=False); line.order = order; line.save(); _audit(request, "ADD_LINE", "Order", order.reference, line.product.sku); messages.success(request, "Order line added.")
        return redirect("order_detail", order_id=order.pk)
    return render(request, "accounts/order_detail.html", {"order": order, "form": form, "lines": order.lines.select_related("product")})


@login_required(login_url="login")
@module_required("management")
def cancel_order(request, order_id):
    if request.method == "POST":
        order = get_object_or_404(Order, pk=order_id)
        if not _manager_required(request): messages.error(request, "Only managers can cancel orders.")
        elif order.status == "FULFILLED": messages.error(request, "Fulfilled orders cannot be cancelled.")
        else:
            order.status = "CANCELLED"; order.save(update_fields=["status", "updated_at"]); _audit(request, "CANCEL", "Order", order.reference); messages.success(request, "Order cancelled.")
    return redirect("orders")


@login_required(login_url="login")
@module_required("management")
def cycle_counts_page(request):
    form = CycleCountForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        obj = form.save(commit=False); obj.expected_quantity = obj.product.quantity; obj.counted_by = request.user; obj.save(); _audit(request, "COUNT", "Cycle count", obj.pk, obj.product.sku); messages.success(request, "Count saved for manager reconciliation."); return redirect("cycle_counts")
    records = CycleCount.objects.select_related("product", "location", "counted_by", "reconciled_by").order_by("-created_at")
    return render(request, "accounts/operations.html", {"title": "Cycle Counts", "form": form, "records": records, "kind": "cycle_counts"})


@login_required(login_url="login")
@module_required("management")
def reconcile_count(request, count_id):
    if request.method != "POST": return redirect("cycle_counts")
    if not _manager_required(request): messages.error(request, "Only managers can reconcile counts."); return redirect("cycle_counts")
    with transaction.atomic():
        count = get_object_or_404(CycleCount.objects.select_for_update(), pk=count_id)
        if count.status != "OPEN": messages.warning(request, "Count already reconciled or cancelled.")
        else:
            product = Product.objects.select_for_update().get(pk=count.product_id)
            delta = count.counted_quantity - count.expected_quantity
            product.quantity = max(0, product.quantity + delta); product.save(update_fields=["quantity"])
            if count.location_id:
                stock, _ = ProductLocation.objects.get_or_create(product=product, location=count.location, defaults={"quantity": 0})
                stock.quantity = count.counted_quantity; stock.save(update_fields=["quantity", "updated_at"])
            count.status, count.reconciled_by, count.reconciled_at = "RECONCILED", request.user, timezone.now(); count.save(update_fields=["status", "reconciled_by", "reconciled_at"])
            _audit(request, "RECONCILE", "Cycle count", count.pk, product.sku); messages.success(request, "Count reconciled.")
    return redirect("cycle_counts")


@login_required(login_url="login")
@module_required("management")
def returns_page(request):
    form = ReturnRecordForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        obj = form.save(commit=False); obj.created_by = request.user; obj.save(); _audit(request, "CREATE", "Return", obj.pk, obj.product.sku); messages.success(request, "Return recorded for inspection."); return redirect("returns")
    records = ReturnRecord.objects.select_related("product", "created_by", "reviewed_by").order_by("-created_at")
    return render(request, "accounts/operations.html", {"title": "Returns and Quarantine", "form": form, "records": records, "kind": "returns"})


@login_required(login_url="login")
@module_required("management")
def review_return(request, return_id, decision):
    if request.method != "POST": return redirect("returns")
    if not _manager_required(request): messages.error(request, "Only managers can review returns."); return redirect("returns")
    with transaction.atomic():
        obj = get_object_or_404(ReturnRecord.objects.select_for_update(), pk=return_id)
        if obj.status != "PENDING": messages.warning(request, "This return has already been reviewed.")
        else:
            product = Product.objects.select_for_update().get(pk=obj.product_id)
            if decision == "restock" and obj.return_type == "CUSTOMER" and obj.condition == "GOOD":
                product.quantity += obj.quantity; product.save(update_fields=["quantity"]); obj.status = "RESTOCKED"
            elif decision == "quarantine": obj.status = "QUARANTINED"
            elif decision == "send" and obj.return_type == "SUPPLIER" and product.quantity >= obj.quantity:
                product.quantity -= obj.quantity; product.save(update_fields=["quantity"]); obj.status = "SENT"
            else: obj.status = "REJECTED"
            obj.reviewed_by, obj.reviewed_at = request.user, timezone.now(); obj.save(update_fields=["status", "reviewed_by", "reviewed_at"])
            _audit(request, obj.status, "Return", obj.pk, product.sku); messages.success(request, f"Return {obj.status.lower()}.")
    return redirect("returns")


@login_required(login_url="login")
@module_required("management")
def batches_page(request):
    form = ProductBatchForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        obj = form.save(); _audit(request, "CREATE", "Batch", obj.batch_number, obj.product.sku); messages.success(request, "Batch saved."); return redirect("batches")
    return render(request, "accounts/operations.html", {"title": "Batch and Expiry Tracking", "form": form, "records": ProductBatch.objects.select_related("product").all(), "kind": "batches"})


@login_required(login_url="login")
@module_required("management")
def export_inventory(request):
    if not _manager_required(request): messages.error(request, "Only staff can export inventory."); return redirect("inventory")
    response = HttpResponse(content_type="text/csv")
    response["Content-Disposition"] = 'attachment; filename="inventory.csv"'
    writer = csv.writer(response)
    writer.writerow(["SKU", "Name", "Barcode", "Category", "Quantity", "UOM", "Reorder level", "Lead time days"])
    for product in Product.objects.order_by("sku"):
        writer.writerow([product.sku, product.name, product.barcode, product.category, product.quantity, product.unit_of_measure, product.reorder_level, product.lead_time_days])
    _audit(request, "EXPORT", "Inventory", "CSV", "Inventory exported")
    return response


@login_required(login_url="login")
@module_required("management")
def staff_roles_page(request):
    if not _manager_required(request):
        messages.error(request, "Only administrators and managers can manage staff roles.")
        return redirect("dashboard")
    if request.method == "POST":
        user = get_object_or_404(User, pk=request.POST.get("user_id"))
        selected = request.POST.getlist("roles")
        role_queryset = StaffRole.objects.filter(code__in=selected)
        if len(set(selected)) != len(selected) or role_queryset.count() != len(set(selected)):
            messages.error(request, "One or more selected roles are invalid.")
        else:
            profile, _ = StaffProfile.objects.get_or_create(user=user)
            profile.roles.set(role_queryset)
            profile.active = request.POST.get("active") == "on"
            profile.save(update_fields=["active"])
            _audit(request, "ROLE_UPDATE", "Staff", user.username, f"roles={','.join(selected)}; active={profile.active}")
            messages.success(request, "Staff roles updated.")
        return redirect("staff_roles")
    users = User.objects.select_related("staff_profile").all().order_by("username")
    return render(request, "accounts/staff_roles.html", {"users": users, "roles": StaffRole.objects.all().order_by("name")})


@login_required(login_url="login")
@module_required("management")
def confirm_delivery(request, shipment_id):
    if request.method != "POST": return redirect("shipping")
    if not _manager_required(request): messages.error(request, "Only managers can confirm delivery."); return redirect("shipping")
    shipment = get_object_or_404(Shipping, pk=shipment_id)
    if shipment.status == "DELIVERED": messages.info(request, "Delivery has already been confirmed.")
    else:
        shipment.status, shipment.delivered_at = "DELIVERED", timezone.now()
        shipment.proof_of_delivery = request.POST.get("proof_of_delivery", "").strip()
        shipment.save(update_fields=["status", "delivered_at", "proof_of_delivery"])
        _audit(request, "DELIVERY_CONFIRMED", "Shipment", shipment.order_ref, "Proof recorded")
        messages.success(request, "Delivery confirmed.")
    return redirect("shipping")


@login_required(login_url="login")
@module_required("management")
def import_inventory(request):
    if not _manager_required(request): messages.error(request, "Only staff can import inventory."); return redirect("inventory")
    if request.method != "POST": return redirect("inventory")
    uploaded = request.FILES.get("file")
    if not uploaded or not uploaded.name.lower().endswith(".csv"):
        messages.error(request, "Choose a CSV file with sku, name and quantity columns."); return redirect("inventory")
    try:
        reader = csv.DictReader(uploaded.read().decode("utf-8-sig").splitlines())
        if not reader.fieldnames or not {h.strip().lower() for h in reader.fieldnames}.issuperset({"sku", "name", "quantity"}):
            raise ValueError("CSV must include sku, name and quantity columns.")
        count = 0
        with transaction.atomic():
            for row in reader:
                row = {str(k).strip().lower(): (v or "").strip() for k, v in row.items() if k}
                sku, name, quantity = row.get("sku", ""), row.get("name", ""), int(row.get("quantity", "0"))
                if not sku or not name or quantity < 0: raise ValueError("Every row needs SKU, name and a non-negative quantity.")
                defaults = {"name": name, "quantity": quantity, "barcode": row.get("barcode", ""), "category": row.get("category", ""), "unit_of_measure": row.get("unit_of_measure", "piece") or "piece", "reorder_level": int(row.get("reorder_level", "5") or 5), "lead_time_days": int(row.get("lead_time_days", "0") or 0)}
                Product.objects.update_or_create(sku=sku, defaults=defaults)
                count += 1
        _audit(request, "IMPORT", "Inventory", "CSV", f"Imported or updated {count} products")
        messages.success(request, f"Imported or updated {count} products.")
    except (UnicodeDecodeError, csv.Error, ValueError, TypeError) as exc:
        messages.error(request, f"Import failed; no rows were saved. Check the CSV: {exc}")
    return redirect("inventory")
