import csv
from datetime import datetime, time, timedelta
from io import BytesIO, StringIO

from django.contrib import messages
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import User
from django.db import transaction
from django.db.models import ExpressionWrapper, F, Q, Sum
from django.http import HttpResponse, HttpResponseBadRequest
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas

from .forms import (
    CustomerForm,
    CycleCountForm,
    OrderForm,
    OrderLineForm,
    PackingForm,
    PickingForm,
    ProductBatchForm,
    PutawayForm,
    ReceivingForm,
    ReturnRecordForm,
    ShippingForm,
    StockAdjustmentForm,
    StockTransferForm,
    SupplierForm,
    WarehouseLocationForm,
)
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
    StaffRole,
    StockAdjustment,
    StockTransfer,
    Supplier,
    WarehouseActivity,
    WarehouseLocation,
)
from .permissions import module_required, modules_for_user


def _audit(request, action, object_type, reference="", details=""):
    AuditLog.objects.create(
        user=request.user if request.user.is_authenticated else None,
        action=action,
        object_type=object_type,
        object_reference=str(reference),
        details=details,
    )


def _activity(activity_type, reference, status="COMPLETED"):
    WarehouseActivity.objects.create(
        activity_type=activity_type,
        reference=str(reference),
        status=status,
    )


def _manager_required(request):
    if request.user.is_superuser or request.user.is_staff:
        return True
    profile = getattr(request.user, "staff_profile", None)
    if not profile or not profile.active:
        return False
    return profile.roles.filter(code__in=("ADMIN", "MANAGER")).exists()


def _manager_denied(request):
    messages.error(request, "Only administrators and managers can perform this action.")
    return redirect("dashboard")


def _operation(request, *, title, kind, form_class, model, order_by="-created_at"):
    if request.method == "POST":
        form = form_class(request.POST)
        if form.is_valid():
            record = form.save(commit=False)
            if kind == "transfers":
                record.requested_by = request.user
            elif kind == "orders":
                record.created_by = request.user
            elif kind == "cycle_counts":
                record.counted_by = request.user
                record.expected_quantity = record.product.quantity
            elif kind == "returns":
                record.created_by = request.user
            record.save()
            messages.success(request, f"{title} record saved.")
            _audit(request, "CREATE", title, record.pk)
            return redirect(kind)
    else:
        form = form_class()
    return render(
        request,
        "accounts/operations.html",
        {
            "title": title,
            "kind": kind,
            "form": form,
            "records": model.objects.all().order_by(order_by),
        },
    )


def login_page(request):
    if request.user.is_authenticated:
        return redirect("dashboard")
    if request.method == "POST":
        user = authenticate(
            request,
            username=request.POST.get("username", "").strip(),
            password=request.POST.get("password", ""),
        )
        if user is not None:
            login(request, user)
            return redirect("dashboard")
        messages.error(request, "Invalid username or password.")
    return render(request, "accounts/index.html")


@login_required(login_url="login")
def register_page(request):
    if not _manager_required(request):
        return _manager_denied(request)
    roles = StaffRole.objects.all()
    context = {"roles": roles, "submitted": {}, "submitted_roles": []}
    if request.method == "POST":
        context["submitted"] = {
            "username": request.POST.get("username", "").strip(),
            "email": request.POST.get("email", "").strip(),
        }
        selected_roles = request.POST.getlist("roles")
        context["submitted_roles"] = selected_roles
        username = context["submitted"]["username"]
        email = context["submitted"]["email"]
        password = request.POST.get("password", "")
        if not username or not email or len(password) < 8:
            messages.error(request, "Enter a username, email, and password of at least 8 characters.")
        elif password != request.POST.get("confirm_password"):
            messages.error(request, "Passwords do not match.")
        elif User.objects.filter(username=username).exists():
            messages.error(request, "That username is already in use.")
        else:
            role_objects = list(StaffRole.objects.filter(code__in=selected_roles))
            if len(role_objects) != len(set(selected_roles)):
                messages.error(request, "One or more selected roles are invalid.")
            else:
                with transaction.atomic():
                    user = User.objects.create_user(
                        username=username, email=email, password=password
                    )
                    profile = StaffProfile.objects.create(
                        user=user, active=request.POST.get("active") == "on"
                    )
                    profile.roles.set(role_objects)
                _audit(request, "CREATE", "Staff", user.username)
                messages.success(request, "Employee account created.")
                return redirect("staff_roles")
    return render(request, "accounts/register.html", context)


@login_required(login_url="login")
@module_required("dashboard")
def dashboard(request):
    allowed = modules_for_user(request.user)
    today = timezone.localdate()
    if "management" in allowed:
        raw_period = request.GET.get("period", "30")
        if raw_period not in {"7", "30", "90"}:
            return HttpResponseBadRequest("Invalid dashboard period.")
        period_days = int(raw_period)
        start_date = today - timedelta(days=period_days - 1)
        start_at = timezone.make_aware(datetime.combine(start_date, time.min))
        end_at = timezone.make_aware(datetime.combine(today + timedelta(days=1), time.min))

        def chart_values(queryset, field_name):
            counts = [0] * 7
            date_range = queryset.filter(
                **{f"{field_name}__gte": start_at, f"{field_name}__lt": end_at}
            ).values_list(field_name, flat=True)
            for value in date_range:
                event_date = (
                    timezone.localtime(value).date()
                    if timezone.is_aware(value)
                    else value.date()
                )
                day_offset = (event_date - start_date).days
                if 0 <= day_offset < period_days:
                    bucket = min(6, day_offset * 7 // period_days)
                    counts[bucket] += 1
            return counts

        trend_values = [
            ("Receiving", "#2878f0", chart_values(Receiving.objects, "received_date")),
            ("Shipping", "#20ad68", chart_values(Shipping.objects, "shipped_at")),
            ("Orders", "#ff9d24", chart_values(Order.objects, "created_at")),
        ]
        chart_max = max(1, max(max(values) for _, _, values in trend_values))
        chart_axis_max = max(4, ((chart_max + 3) // 4) * 4)
        chart_points = []
        chart_series = []
        for index in range(7):
            label_day = start_date + timedelta(
                days=(index * (period_days - 1) + 3) // 6
            )
            chart_points.append(
                {
                    "x": 48 + index * 90,
                    "label": label_day.strftime("%a" if period_days == 7 else "%b %d"),
                }
            )
        for name, color, values in trend_values:
            points = [
                {
                    "x": chart_points[index]["x"],
                    "y": round(204 - (value / chart_axis_max) * 176, 1),
                }
                for index, value in enumerate(values)
            ]
            chart_series.append(
                {
                    "name": name,
                    "color": color,
                    "points": points,
                    "point_string": " ".join(
                        f'{point["x"]},{point["y"]}' for point in points
                    ),
                }
            )

        product_count = Product.objects.count()
        in_stock_count = Product.objects.filter(
            quantity__gt=F("reorder_level")
        ).count()
        low_stock_count = Product.objects.filter(
            quantity__gt=0, quantity__lte=F("reorder_level")
        ).count()
        out_of_stock_count = Product.objects.filter(quantity=0).count()
        stock_total = in_stock_count + low_stock_count + out_of_stock_count
        stock_percentages = {
            "in_stock": round(in_stock_count * 100 / stock_total) if stock_total else 0,
            "low_stock": round(low_stock_count * 100 / stock_total) if stock_total else 0,
            "out_of_stock": round(out_of_stock_count * 100 / stock_total) if stock_total else 0,
        }

        employee_count = StaffProfile.objects.count()
        active_employee_count = StaffProfile.objects.filter(
            active=True, user__is_active=True
        ).count()
        product_units = Product.objects.aggregate(total=Sum("quantity"))["total"] or 0
        receipt_count = Receiving.objects.count()
        putaway_count = Receiving.objects.filter(inventory_updated=True).count()
        active_order_count = Order.objects.exclude(
            status__in=("DRAFT", "CANCELLED")
        ).count()
        fulfilled_order_count = Order.objects.filter(status="FULFILLED").count()
        shipment_count = Shipping.objects.count()
        delivered_shipment_count = Shipping.objects.filter(status="DELIVERED").count()

        def performance_metric(label, completed, total, color):
            return {
                "label": label,
                "completed": completed,
                "total": total,
                "percent": round(completed * 100 / total) if total else None,
                "color": color,
            }

        return render(
            request,
            "accounts/manager_dashboard.html",
            {
                "period": raw_period,
                "employee_count": employee_count,
                "active_employee_count": active_employee_count,
                "product_count": product_count,
                "product_units": product_units,
                "low_stock_count": low_stock_count,
                "pending_order_count": Order.objects.filter(
                    status__in=("OPEN", "PARTIALLY_FULFILLED")
                ).count(),
                "pending_receiving_count": Receiving.objects.filter(
                    status="RECEIVED", inventory_updated=False
                ).count(),
                "pending_approval_count": StockAdjustment.objects.filter(
                    status="PENDING"
                ).count(),
                "in_stock_count": in_stock_count,
                "out_of_stock_count": out_of_stock_count,
                "stock_percentages": stock_percentages,
                "trend_series": chart_series,
                "trend_points": chart_points,
                "trend_grid": [
                    {
                        "y": 28 + index * 44,
                        "label": chart_axis_max - index * (chart_axis_max // 4),
                    }
                    for index in range(5)
                ],
                "recent_activities": AuditLog.objects.select_related("user").order_by(
                    "-created_at"
                )[:5],
                "performance_metrics": [
                    performance_metric(
                        "Putaway completion", putaway_count, receipt_count, "blue"
                    ),
                    performance_metric(
                        "Order fulfillment",
                        fulfilled_order_count,
                        active_order_count,
                        "green",
                    ),
                    performance_metric(
                        "Shipment delivery",
                        delivered_shipment_count,
                        shipment_count,
                        "orange",
                    ),
                ],
                "accessible_modules": allowed,
            },
        )

    dashboard_cards = []
    activity_types = []

    def add_dashboard_card(
        module, title, value, detail, icon, url_name, activity_type, color
    ):
        if module not in allowed:
            return
        dashboard_cards.append(
            {
                "title": title,
                "value": value,
                "detail": detail,
                "icon": icon,
                "url": reverse(url_name),
                "color": color,
            }
        )
        activity_types.append(activity_type)

    if "receiving" in allowed:
        add_dashboard_card(
            "receiving",
            "Receiving",
            Receiving.objects.count(),
            "Receipt records",
            "fa-truck-ramp-box",
            "receiving",
            "RECEIVING",
            "blue-card",
        )
    if "putaway" in allowed:
        add_dashboard_card(
            "putaway",
            "Putaway",
            Receiving.objects.filter(status="RECEIVED", inventory_updated=False).count(),
            "Receipts awaiting putaway",
            "fa-dolly",
            "putaway",
            "PUTAWAY",
            "green-card",
        )
    if "inventory" in allowed:
        low_stock_count = Product.objects.filter(
            quantity__gt=0, quantity__lte=F("reorder_level")
        ).count()
        add_dashboard_card(
            "inventory",
            "Inventory",
            Product.objects.count(),
            f"{low_stock_count} low-stock products",
            "fa-boxes-stacked",
            "inventory",
            "INVENTORY",
            "cyan-card",
        )
    if "picking" in allowed:
        add_dashboard_card(
            "picking",
            "Picking",
            Picking.objects.count(),
            "Picking tasks recorded",
            "fa-hand-pointer",
            "picking",
            "PICKING",
            "purple-card",
        )
    if "packing" in allowed:
        add_dashboard_card(
            "packing",
            "Packing",
            Packing.objects.count(),
            "Packed records",
            "fa-box",
            "packing",
            "PACKING",
            "amber-card",
        )
    if "shipping" in allowed:
        add_dashboard_card(
            "shipping",
            "Shipping",
            Shipping.objects.filter(status="IN_TRANSIT").count(),
            "Shipments in transit",
            "fa-truck-fast",
            "shipping",
            "SHIPPING",
            "mint-card",
        )
    dashboard_title = (
        f'{dashboard_cards[0]["title"]} Dashboard'
        if len(dashboard_cards) == 1
        else "My Warehouse Dashboard"
    )
    if not dashboard_cards:
        dashboard_title = "Warehouse Dashboard"

    expiry_batches = []
    if "receiving" in allowed:
        expiry_limit = today + timedelta(days=30)
        batches = ProductBatch.objects.filter(
            expiry_date__isnull=False, expiry_date__lte=expiry_limit
        ).select_related("product")
        expiry_batches = [
            {
                "product_name": batch.product.name,
                "sku": batch.product.sku,
                "quantity": batch.quantity,
                "expiry_date": batch.expiry_date,
                "row_class": "danger" if batch.expiry_date < today else "warning",
            }
            for batch in batches
        ]

    return render(
        request,
        "accounts/role_dashboard.html",
        {
            "accessible_modules": allowed,
            "dashboard_cards": dashboard_cards,
            "dashboard_title": dashboard_title,
            "dashboard_description": (
                "A focused overview of the warehouse work assigned to your account."
                if dashboard_cards
                else "No warehouse work modules are assigned to your account. Ask a manager to update your roles."
            ),
            "expiring_batches": expiry_batches,
            "recent_activities": WarehouseActivity.objects.filter(
                activity_type__in=activity_types
            ).order_by("-created_at")[:8],
        },
    )


@login_required(login_url="login")
def logout_page(request):
    if request.method == "POST":
        logout(request)
        return redirect("login")
    return render(request, "accounts/logout.html")


@login_required(login_url="login")
@module_required("receiving")
def receiving_page(request):
    form = ReceivingForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        record = form.save()
        _activity("RECEIVING", record.sku)
        _audit(request, "RECEIVE", "Receiving", record.sku)
        messages.success(request, "Goods received. Inventory will update after putaway.")
        return redirect("receiving")
    return render(
        request,
        "accounts/receiving.html",
        {"form": form, "records": Receiving.objects.order_by("-received_date")},
    )


@login_required(login_url="login")
@module_required("putaway")
def putaway_page(request):
    form = PutawayForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        with transaction.atomic():
            receiving = Receiving.objects.select_for_update().get(
                pk=form.cleaned_data["receiving"].pk
            )
            if receiving.status != "RECEIVED" or receiving.inventory_updated:
                form.add_error("receiving", "This receipt has already been put away.")
            elif receiving.condition != Receiving.CONDITION_GOOD:
                form.add_error("receiving", "Damaged goods cannot be added to inventory.")
            else:
                record = form.save(commit=False)
                record.receiving = receiving
                record.save()
                product, _ = Product.objects.get_or_create(
                    sku=receiving.sku,
                    defaults={"name": receiving.product_name},
                )
                product.name = receiving.product_name
                product.quantity = F("quantity") + receiving.quantity
                product.save(update_fields=("name", "quantity"))
                product.refresh_from_db(fields=("quantity",))
                if record.location_ref_id:
                    stock, _ = ProductLocation.objects.get_or_create(
                        product=product, location=record.location_ref
                    )
                    stock.quantity = F("quantity") + receiving.quantity
                    stock.save(update_fields=("quantity", "updated_at"))
                if receiving.batch_number:
                    ProductBatch.objects.update_or_create(
                        product=product,
                        batch_number=receiving.batch_number,
                        defaults={
                            "quantity": receiving.quantity,
                            "received_date": receiving.received_date.date(),
                            "expiry_date": receiving.expiry_date,
                        },
                    )
                receiving.status = "STORED"
                receiving.inventory_updated = True
                receiving.save(update_fields=("status", "inventory_updated"))
                _activity("PUTAWAY", receiving.sku)
                _audit(request, "PUTAWAY", "Receiving", receiving.sku)
                messages.success(request, "Putaway saved and inventory updated.")
                return redirect("putaway")
    return render(
        request,
        "accounts/putaway.html",
        {"form": form, "records": Putaway.objects.select_related("receiving").order_by("-created_at")},
    )


@login_required(login_url="login")
@module_required("inventory")
def inventory_page(request):
    query = request.GET.get("q", "").strip()
    products = Product.objects.all().order_by("name")
    if query:
        search = Q()
        for field in ("name", "sku", "barcode", "category"):
            search |= Q(**{f"{field}__icontains": query})
        products = products.filter(search)
    return render(
        request,
        "accounts/inventory.html",
        {
            "products": products,
            "query": query,
            "low_stock": products.filter(quantity__lte=F("reorder_level")),
        },
    )

@login_required(login_url="login")
@module_required("picking")
def picking_page(request):
    form = PickingForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        product = form.cleaned_data["product"]
        quantity = form.cleaned_data["quantity"]
        with transaction.atomic():
            product = Product.objects.select_for_update().get(pk=product.pk)
            if product.quantity < quantity:
                form.add_error("quantity", "Quantity exceeds available inventory.")
            else:
                record = Picking.objects.create(
                    product_name=product.name,
                    sku=product.sku,
                    quantity=quantity,
                    order_reference=form.cleaned_data["order_reference"],
                    status="COMPLETED",
                )
                product.quantity = F("quantity") - quantity
                product.save(update_fields=("quantity",))
                _activity("PICKING", record.order_reference)
                _audit(request, "PICK", "Picking", record.order_reference, product.sku)
                messages.success(request, "Picking task saved and inventory reduced.")
                return redirect("picking")
    return render(
        request,
        "accounts/picking.html",
        {"form": form, "records": Picking.objects.order_by("-created_at")},
    )


@login_required(login_url="login")
@module_required("packing")
def packing_page(request):
    form = PackingForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        order_ref = form.cleaned_data["order_ref"]
        product = form.cleaned_data["product"]
        quantity = form.cleaned_data["quantity"]
        picked = Picking.objects.filter(
            order_reference=order_ref, sku=product.sku
        ).aggregate(total=Sum("quantity"))["total"] or 0
        packed = Packing.objects.filter(
            order_ref=order_ref, product=product
        ).aggregate(total=Sum("quantity"))["total"] or 0
        if quantity > picked - packed:
            form.add_error("quantity", "Quantity exceeds the remaining picked amount.")
        else:
            record = form.save()
            _activity("PACKING", order_ref)
            _audit(request, "PACK", "Packing", order_ref, product.sku)
            messages.success(request, "Packing record saved.")
            return redirect("packing")
    return render(
        request,
        "accounts/packing.html",
        {"form": form, "records": Packing.objects.select_related("product").order_by("-created_at")},
    )


@login_required(login_url="login")
@module_required("shipping")
def shipping_page(request):
    form = ShippingForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        order_ref = form.cleaned_data["order_ref"]
        product = form.cleaned_data["product"]
        quantity = form.cleaned_data["quantity"]
        packed = Packing.objects.filter(
            order_ref=order_ref, product=product
        ).aggregate(total=Sum("quantity"))["total"] or 0
        shipped = Shipping.objects.filter(
            order_ref=order_ref, product=product
        ).aggregate(total=Sum("quantity"))["total"] or 0
        if quantity > packed - shipped:
            form.add_error("quantity", "Quantity exceeds the remaining packed amount.")
        else:
            record = form.save()
            _activity("SHIPPING", order_ref, "IN_PROGRESS")
            _audit(request, "SHIP", "Shipping", order_ref, product.sku)
            messages.success(request, "Shipment created.")
            return redirect("shipping")
    return render(
        request,
        "accounts/shipping.html",
        {"form": form, "records": Shipping.objects.select_related("product").order_by("-shipped_at")},
    )


@login_required(login_url="login")
@module_required("management")
def suppliers_page(request):
    return _master_data(request, "Suppliers", SupplierForm, Supplier, ("code", "name", "contact_person", "email", "phone"))


@login_required(login_url="login")
@module_required("management")
def customers_page(request):
    return _master_data(request, "Customers", CustomerForm, Customer, ("code", "name", "contact_person", "email", "phone"))


@login_required(login_url="login")
@module_required("management")
def locations_page(request):
    return _master_data(request, "Locations", WarehouseLocationForm, WarehouseLocation, ("warehouse", "zone", "aisle", "rack", "bin", "is_active"))


def _master_data(request, title, form_class, model, columns):
    form = form_class(request.POST or None)
    if request.method == "POST" and form.is_valid():
        record = form.save()
        _audit(request, "CREATE", title, record.pk)
        messages.success(request, f"{title[:-1]} saved.")
        return redirect(request.resolver_match.url_name)
    return render(
        request,
        "accounts/master_data.html",
        {
            "page_title": title,
            "form": form,
            "records": model.objects.all().order_by("pk"),
            "columns": columns,
        },
    )


@login_required(login_url="login")
@module_required("management")
def adjustments_page(request):
    form = StockAdjustmentForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        record = form.save(commit=False)
        record.requested_by = request.user
        record.save()
        _audit(request, "REQUEST", "Stock adjustment", record.pk)
        messages.success(request, "Adjustment submitted for approval.")
        return redirect("adjustments")
    return render(
        request,
        "accounts/adjustments.html",
        {"form": form, "records": StockAdjustment.objects.select_related("product", "requested_by").order_by("-created_at")},
    )


@login_required(login_url="login")
@module_required("management")
def review_adjustment(request, adjustment_id, decision):
    if request.method != "POST":
        return HttpResponseBadRequest("A POST request is required.")
    if not _manager_required(request):
        return _manager_denied(request)
    adjustment = get_object_or_404(
        StockAdjustment.objects.select_related("product"),
        pk=adjustment_id,
        status="PENDING",
    )
    if decision not in ("approve", "reject"):
        return HttpResponseBadRequest("Unknown adjustment decision.")
    if decision == "approve":
        with transaction.atomic():
            product = Product.objects.select_for_update().get(pk=adjustment.product_id)
            new_quantity = product.quantity + adjustment.change_quantity
            if new_quantity < 0:
                messages.error(request, "This adjustment would make inventory negative.")
                return redirect("adjustments")
            product.quantity = new_quantity
            product.save(update_fields=("quantity",))
            adjustment.status = "APPROVED"
        _activity("INVENTORY", adjustment.product.sku)
    else:
        adjustment.status = "REJECTED"
    adjustment.approved_by = request.user
    adjustment.reviewed_at = timezone.now()
    adjustment.save(update_fields=("status", "approved_by", "reviewed_at"))
    _audit(request, decision.upper(), "Stock adjustment", adjustment.pk)
    messages.success(request, "Adjustment approved." if decision == "approve" else "Adjustment rejected.")
    return redirect("adjustments")


@login_required(login_url="login")
@module_required("management")
def reports_page(request):
    return render(
        request,
        "accounts/reports.html",
        {
            "supplier_count": Supplier.objects.count(),
            "customer_count": Customer.objects.count(),
            "location_count": WarehouseLocation.objects.filter(is_active=True).count(),
            "adjustments_pending": StockAdjustment.objects.filter(status="PENDING").count(),
            "low_stock": Product.objects.filter(quantity__lte=F("reorder_level")).order_by("quantity", "name"),
            "recent_audit": AuditLog.objects.select_related("user")[:50],
        },
    )


@login_required(login_url="login")
@module_required("dashboard")
def download_report(request):
    period = request.GET.get("period")
    if period not in ("daily", "weekly", "monthly"):
        return HttpResponseBadRequest("Choose daily, weekly, or monthly.")
    buffer = BytesIO()
    pdf = canvas.Canvas(buffer, pagesize=letter)
    pdf.setTitle(f"Warehouse {period} report")
    pdf.drawString(72, 740, f"Warehouse {period.title()} Report")
    pdf.drawString(72, 716, f"Generated: {timezone.localtime():%Y-%m-%d %H:%M}")
    y = 680
    for label, count in (
        ("Receiving records", Receiving.objects.count()),
        ("Putaway records", Putaway.objects.count()),
        ("Products", Product.objects.count()),
        ("Picking tasks", Picking.objects.count()),
        ("Packing records", Packing.objects.count()),
        ("Shipments", Shipping.objects.count()),
    ):
        pdf.drawString(72, y, f"{label}: {count}")
        y -= 22
    pdf.save()
    response = HttpResponse(buffer.getvalue(), content_type="application/pdf")
    response["Content-Disposition"] = f'attachment; filename="warehouse-{period}-report.pdf"'
    return response


@login_required(login_url="login")
@module_required("management")
def transfers_page(request):
    return _operation(request, title="Stock transfer", kind="transfers", form_class=StockTransferForm, model=StockTransfer)


@login_required(login_url="login")
@module_required("management")
def complete_transfer(request, transfer_id):
    if request.method != "POST":
        return HttpResponseBadRequest("A POST request is required.")
    if not _manager_required(request):
        return _manager_denied(request)
    with transaction.atomic():
        transfer = get_object_or_404(
            StockTransfer.objects.select_for_update().select_related("product", "source", "destination"),
            pk=transfer_id,
            status="PENDING",
        )
        source_stock = ProductLocation.objects.select_for_update().filter(
            product=transfer.product, location=transfer.source
        ).first()
        if not source_stock or source_stock.quantity < transfer.quantity:
            messages.error(request, "The source location does not have enough stock.")
            return redirect("transfers")
        destination_stock, _ = ProductLocation.objects.get_or_create(
            product=transfer.product, location=transfer.destination
        )
        source_stock.quantity = F("quantity") - transfer.quantity
        destination_stock.quantity = F("quantity") + transfer.quantity
        source_stock.save(update_fields=("quantity", "updated_at"))
        destination_stock.save(update_fields=("quantity", "updated_at"))
        transfer.status = "COMPLETED"
        transfer.completed_at = timezone.now()
        transfer.save(update_fields=("status", "completed_at"))
    _audit(request, "COMPLETE", "Stock transfer", transfer.pk)
    messages.success(request, "Stock transfer completed.")
    return redirect("transfers")


@login_required(login_url="login")
@module_required("management")
def orders_page(request):
    return _operation(request, title="Customer order", kind="orders", form_class=OrderForm, model=Order)


@login_required(login_url="login")
@module_required("management")
def order_detail(request, order_id):
    order = get_object_or_404(Order.objects.select_related("customer"), pk=order_id)
    form = OrderLineForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        line = form.save(commit=False)
        line.order = order
        line.save()
        _audit(request, "ADD_LINE", "Order", order.reference, line.product.sku)
        messages.success(request, "Order line added.")
        return redirect("order_detail", order_id=order.pk)
    lines = order.lines.select_related("product").annotate(
        line_total=ExpressionWrapper(
            F("quantity") * F("unit_price"),
            output_field=OrderLine._meta.get_field("unit_price"),
        )
    )
    return render(
        request,
        "accounts/order_detail.html",
        {"order": order, "form": form, "lines": lines},
    )


@login_required(login_url="login")
@module_required("management")
def cancel_order(request, order_id):
    if request.method != "POST":
        return HttpResponseBadRequest("A POST request is required.")
    order = get_object_or_404(Order, pk=order_id)
    if order.status not in ("CANCELLED", "FULFILLED"):
        order.status = "CANCELLED"
        order.save(update_fields=("status", "updated_at"))
        _audit(request, "CANCEL", "Order", order.reference)
        messages.success(request, "Order cancelled.")
    return redirect("orders")


@login_required(login_url="login")
@module_required("management")
def cycle_counts_page(request):
    return _operation(request, title="Cycle count", kind="cycle_counts", form_class=CycleCountForm, model=CycleCount)


@login_required(login_url="login")
@module_required("management")
def reconcile_count(request, count_id):
    if request.method != "POST":
        return HttpResponseBadRequest("A POST request is required.")
    if not _manager_required(request):
        return _manager_denied(request)
    with transaction.atomic():
        count = get_object_or_404(
            CycleCount.objects.select_for_update().select_related("product"),
            pk=count_id,
            status="OPEN",
        )
        product = Product.objects.select_for_update().get(pk=count.product_id)
        product.quantity = count.counted_quantity
        product.save(update_fields=("quantity",))
        count.status = "RECONCILED"
        count.reconciled_by = request.user
        count.reconciled_at = timezone.now()
        count.save(update_fields=("status", "reconciled_by", "reconciled_at"))
    _audit(request, "RECONCILE", "Cycle count", count.pk)
    messages.success(request, "Cycle count reconciled.")
    return redirect("cycle_counts")


@login_required(login_url="login")
@module_required("management")
def returns_page(request):
    return _operation(request, title="Return", kind="returns", form_class=ReturnRecordForm, model=ReturnRecord)


@login_required(login_url="login")
@module_required("management")
def review_return(request, return_id, decision):
    if request.method != "POST":
        return HttpResponseBadRequest("A POST request is required.")
    if not _manager_required(request):
        return _manager_denied(request)
    with transaction.atomic():
        record = get_object_or_404(
            ReturnRecord.objects.select_for_update().select_related("product"),
            pk=return_id,
            status="PENDING",
        )
        if decision == "restock":
            if record.return_type != "CUSTOMER" or record.condition != "GOOD":
                return HttpResponseBadRequest("Only good customer returns can be restocked.")
            product = Product.objects.select_for_update().get(pk=record.product_id)
            product.quantity = F("quantity") + record.quantity
            product.save(update_fields=("quantity",))
            record.status = "RESTOCKED"
        elif decision == "quarantine":
            record.status = "QUARANTINED"
        elif decision == "send" and record.return_type == "SUPPLIER":
            record.status = "SENT"
        else:
            return HttpResponseBadRequest("Unknown return decision.")
        record.reviewed_by = request.user
        record.reviewed_at = timezone.now()
        record.save(update_fields=("status", "reviewed_by", "reviewed_at"))
    _audit(request, decision.upper(), "Return", record.pk)
    messages.success(request, "Return updated.")
    return redirect("returns")


@login_required(login_url="login")
@module_required("management")
def batches_page(request):
    form = ProductBatchForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        batch = form.save()
        _audit(request, "CREATE", "Product batch", batch.batch_number)
        messages.success(request, "Batch saved.")
        return redirect("batches")
    return render(
        request,
        "accounts/operations.html",
        {
            "title": "Product batch",
            "kind": "batches",
            "form": form,
            "records": ProductBatch.objects.select_related("product").order_by("-pk"),
        },
    ) if request.method != "POST" or not form.is_valid() else redirect("batches")


@login_required(login_url="login")
@module_required("management")
def export_inventory(request):
    output = StringIO()
    writer = csv.writer(output)
    writer.writerow(("name", "sku", "quantity", "barcode", "category", "unit_of_measure", "reorder_level", "lead_time_days"))
    for product in Product.objects.order_by("sku"):
        writer.writerow((product.name, product.sku, product.quantity, product.barcode, product.category, product.unit_of_measure, product.reorder_level, product.lead_time_days))
    response = HttpResponse(output.getvalue(), content_type="text/csv; charset=utf-8")
    response["Content-Disposition"] = 'attachment; filename="inventory.csv"'
    return response


@login_required(login_url="login")
@module_required("management")
def import_inventory(request):
    if request.method != "POST":
        return HttpResponseBadRequest("A POST request is required.")
    uploaded = request.FILES.get("file")
    if not uploaded:
        messages.error(request, "Select a CSV file to import.")
        return redirect("inventory")
    try:
        text = uploaded.read().decode("utf-8-sig")
        reader = csv.DictReader(StringIO(text))
        required = {"name", "sku", "quantity"}
        if not reader.fieldnames or not required.issubset(set(reader.fieldnames)):
            raise ValueError("CSV must include name, sku, and quantity columns.")
        rows = list(reader)
        parsed = []
        for row_number, row in enumerate(rows, start=2):
            name, sku = (row.get("name") or "").strip(), (row.get("sku") or "").strip()
            quantity = int(row.get("quantity", ""))
            reorder_level = int(row.get("reorder_level") or 5)
            lead_time_days = int(row.get("lead_time_days") or 0)
            if not name or not sku or quantity < 0:
                raise ValueError(f"Invalid name, SKU, or quantity on row {row_number}.")
            if reorder_level < 0 or lead_time_days < 0:
                raise ValueError(f"Invalid stock threshold or lead time on row {row_number}.")
            parsed.append((row, name, sku, quantity, reorder_level, lead_time_days))
    except (UnicodeDecodeError, csv.Error, TypeError, ValueError) as exc:
        messages.error(request, f"Import failed: {exc}")
        return redirect("inventory")
    with transaction.atomic():
        for row, name, sku, quantity, reorder_level, lead_time_days in parsed:
            Product.objects.update_or_create(
                sku=sku,
                defaults={
                    "name": name,
                    "quantity": quantity,
                    "barcode": row.get("barcode", ""),
                    "category": row.get("category", ""),
                    "unit_of_measure": row.get("unit_of_measure") or "piece",
                    "reorder_level": reorder_level,
                    "lead_time_days": lead_time_days,
                },
            )
    messages.success(request, f"Imported {len(parsed)} inventory records.")
    return redirect("inventory")


@login_required(login_url="login")
@module_required("management")
def staff_roles_page(request):
    if not _manager_required(request):
        return _manager_denied(request)
    if request.method == "POST":
        user = get_object_or_404(User, pk=request.POST.get("user_id"))
        selected_codes = request.POST.getlist("roles")
        role_queryset = StaffRole.objects.filter(code__in=selected_codes)
        if len(selected_codes) != role_queryset.count() or len(selected_codes) != len(set(selected_codes)):
            messages.error(request, "One or more selected roles are invalid.")
        else:
            profile, _ = StaffProfile.objects.get_or_create(user=user)
            profile.roles.set(role_queryset)
            profile.active = request.POST.get("active") == "on"
            profile.save(update_fields=("active",))
            _audit(request, "ROLE_UPDATE", "Staff", user.username, f"roles={','.join(selected_codes)}; active={profile.active}")
            messages.success(request, "Staff roles updated.")
        return redirect("staff_roles")
    return render(
        request,
        "accounts/staff_roles.html",
        {
            "users": User.objects.prefetch_related("staff_profile__roles").order_by("username"),
            "roles": StaffRole.objects.all(),
        },
    )


@login_required(login_url="login")
@module_required("management")
def confirm_delivery(request, shipment_id):
    if request.method != "POST":
        return HttpResponseBadRequest("A POST request is required.")
    shipment = get_object_or_404(Shipping, pk=shipment_id)
    if shipment.status == "DELIVERED":
        messages.info(request, "This shipment is already marked delivered.")
    else:
        shipment.status = "DELIVERED"
        shipment.proof_of_delivery = request.POST.get("proof_of_delivery", "").strip()
        shipment.delivered_at = timezone.now()
        shipment.save(update_fields=("status", "proof_of_delivery", "delivered_at"))
        _audit(request, "DELIVER", "Shipping", shipment.pk, shipment.proof_of_delivery)
        messages.success(request, "Delivery confirmed.")
    return redirect("shipping")
