from django import forms
from django.db.models import Sum
from .models import Packing, Picking, Product, Putaway, Receiving, Shipping


class StyledModelForm(forms.ModelForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            field.widget.attrs.setdefault("class", "form-control")


class ReceivingForm(StyledModelForm):
    class Meta:
        model = Receiving
        fields = [
            "product_name", "sku", "quantity", "unit_price",
<<<<<<< HEAD
            "supplier", "expiry_date", "condition",
=======
            "supplier", "supplier_record", "batch_number", "expiry_date", "condition",
>>>>>>> origin/main
        ]
        widgets = {
            "quantity": forms.NumberInput(attrs={"min": 1}),
            "unit_price": forms.NumberInput(attrs={"min": 0, "step": "0.01"}),
            "expiry_date": forms.DateInput(attrs={"type": "date"}),
        }

    def clean_quantity(self):
        value = self.cleaned_data["quantity"]
        if value <= 0:
            raise forms.ValidationError("Quantity must be greater than zero.")
        return value

    def clean_unit_price(self):
        value = self.cleaned_data["unit_price"]
        if value < 0:
            raise forms.ValidationError("Unit price cannot be negative.")
        return value


class PutawayForm(StyledModelForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["receiving"].queryset = Receiving.objects.filter(
            status="RECEIVED",
            condition=Receiving.CONDITION_GOOD,
        ).order_by("-received_date")
        self.fields["receiving"].label_from_instance = self.receiving_label

    @staticmethod
    def receiving_label(receiving):
        return f"{receiving.product_name} — SKU {receiving.sku} — Qty {receiving.quantity}"

    class Meta:
        model = Putaway
<<<<<<< HEAD
        fields = ["receiving", "location"]
=======
        fields = ["receiving", "location", "location_ref"]
>>>>>>> origin/main

    def clean_location(self):
        value = self.cleaned_data["location"].strip()
        if not value:
            raise forms.ValidationError("Storage location is required.")
        return value


class PickingForm(StyledModelForm):
    product = forms.ModelChoiceField(
        queryset=Product.objects.none(),
        label="Product from inventory",
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["product"].queryset = Product.objects.filter(
            quantity__gt=0,
        ).order_by("name")
        self.fields["product"].label_from_instance = self.product_label

    @staticmethod
    def product_label(product):
        return f"{product.name} — SKU {product.sku} — Available: {product.quantity}"

    class Meta:
        model = Picking
        fields = ["product", "quantity", "order_reference"]
        widgets = {
            "quantity": forms.NumberInput(attrs={"min": 1}),
            "order_reference": forms.TextInput(attrs={"placeholder": "e.g. ORD-1001"}),
        }

    def clean_quantity(self):
        value = self.cleaned_data["quantity"]
        if value <= 0:
            raise forms.ValidationError("Quantity must be greater than zero.")
        return value


class PackingForm(StyledModelForm):
    order_ref = forms.ChoiceField(label="Order Reference")

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        picked = {
            (row["order_reference"], row["sku"]): row["quantity"]
            for row in Picking.objects.values("order_reference", "sku").annotate(
                quantity=Sum("quantity")
            )
        }
        packed = {
            (row["order_ref"], row["product__sku"]): row["quantity"]
            for row in Packing.objects.values("order_ref", "product__sku").annotate(
                quantity=Sum("quantity")
            )
        }
        remaining = {
            key: quantity - packed.get(key, 0)
            for key, quantity in picked.items()
            if quantity > packed.get(key, 0)
        }
        order_refs = sorted({order_ref for order_ref, _ in remaining})
        self.fields["order_ref"].choices = [("", "Select an order")] + [
            (order_ref, order_ref) for order_ref in order_refs
        ]
        self.fields["order_ref"].widget.attrs["onchange"] = (
            "this.form.method='get'; this.form.submit()"
        )

        selected_order = self.data.get(self.add_prefix("order_ref")) or self.initial.get(
            "order_ref"
        )
        products_remaining = {
            sku: quantity
            for (order_ref, sku), quantity in remaining.items()
            if order_ref == selected_order
        }
        self.fields["product"].queryset = Product.objects.filter(
            sku__in=products_remaining,
        ).order_by("name")
        self.fields["product"].label_from_instance = (
            lambda product: (
                f"{product.name} — SKU {product.sku} — "
                f"Remaining to pack: {products_remaining[product.sku]}"
            )
        )

    class Meta:
        model = Packing
        fields = ["order_ref", "product", "quantity"]
        widgets = {
            "quantity": forms.NumberInput(attrs={"min": 1}),
        }

    def clean_quantity(self):
        value = self.cleaned_data["quantity"]
        if value <= 0:
            raise forms.ValidationError("Quantity must be greater than zero.")
        return value


class ShippingForm(StyledModelForm):
    order_ref = forms.ChoiceField(label="Order Reference")

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        packed = {
            (row["order_ref"], row["product__sku"]): row["quantity"]
            for row in Packing.objects.values("order_ref", "product__sku").annotate(
                quantity=Sum("quantity")
            )
        }
        shipped = {
            (row["order_ref"], row["product__sku"]): row["quantity"]
            for row in Shipping.objects.values("order_ref", "product__sku").annotate(
                quantity=Sum("quantity")
            )
        }
        remaining = {
            key: quantity - shipped.get(key, 0)
            for key, quantity in packed.items()
            if quantity > shipped.get(key, 0)
        }
        order_refs = sorted({order_ref for order_ref, _ in remaining})
        self.fields["order_ref"].choices = [("", "Select an order")] + [
            (order_ref, order_ref) for order_ref in order_refs
        ]
        self.fields["order_ref"].widget.attrs["onchange"] = (
            "this.form.method='get'; this.form.submit()"
        )

        selected_order = self.data.get(self.add_prefix("order_ref")) or self.initial.get(
            "order_ref"
        )
        products_remaining = {
            sku: quantity
            for (order_ref, sku), quantity in remaining.items()
            if order_ref == selected_order
        }
        self.fields["product"].queryset = Product.objects.filter(
            sku__in=products_remaining,
        ).order_by("name")
        self.fields["product"].label_from_instance = (
            lambda product: (
                f"{product.name} — SKU {product.sku} — "
                f"Remaining to ship: {products_remaining[product.sku]}"
            )
        )

    class Meta:
        model = Shipping
<<<<<<< HEAD
        fields = ["order_ref", "product", "quantity", "destination"]
=======
        fields = ["order_ref", "product", "quantity", "destination", "carrier", "tracking_number"]
>>>>>>> origin/main
        widgets = {
            "quantity": forms.NumberInput(attrs={"min": 1}),
            "destination": forms.TextInput(attrs={"placeholder": "Customer / delivery address"}),
        }

    def clean_quantity(self):
        value = self.cleaned_data["quantity"]
        if value <= 0:
            raise forms.ValidationError("Quantity must be greater than zero.")
        return value

    def clean_destination(self):
        value = self.cleaned_data["destination"].strip()
        if not value:
            raise forms.ValidationError("Destination is required.")
        return value
<<<<<<< HEAD
=======

from .models import Customer, Supplier, WarehouseLocation, StockAdjustment

class SupplierForm(StyledModelForm):
    class Meta:
        model = Supplier
        fields = ["code", "name", "contact_person", "email", "phone", "address"]

class CustomerForm(StyledModelForm):
    class Meta:
        model = Customer
        fields = ["code", "name", "contact_person", "email", "phone", "billing_address", "shipping_address"]

class WarehouseLocationForm(StyledModelForm):
    class Meta:
        model = WarehouseLocation
        fields = ["warehouse", "zone", "aisle", "rack", "bin", "is_active"]

class StockAdjustmentForm(StyledModelForm):
    class Meta:
        model = StockAdjustment
        fields = ["product", "change_quantity", "reason", "notes"]
        widgets = {"change_quantity": forms.NumberInput(attrs={"placeholder": "e.g. -3 or 10"})}

    def clean_change_quantity(self):
        value = self.cleaned_data["change_quantity"]
        if value == 0:
            raise forms.ValidationError("Adjustment must change stock by at least one unit.")
        return value

from .models import Order, OrderLine, CycleCount, ReturnRecord, StockTransfer, ProductBatch

class StockTransferForm(StyledModelForm):
    class Meta:
        model = StockTransfer
        fields = ['product','source','destination','quantity']
        widgets = {'quantity': forms.NumberInput(attrs={'min': 1})}
    def clean(self):
        cleaned = super().clean()
        if cleaned.get('source') == cleaned.get('destination'):
            raise forms.ValidationError('Source and destination must be different locations.')
        if cleaned.get('quantity', 0) <= 0:
            raise forms.ValidationError('Quantity must be greater than zero.')
        return cleaned

class OrderForm(StyledModelForm):
    class Meta:
        model = Order
        fields = ['reference','customer','shipping_address','billing_address','notes']

class OrderLineForm(StyledModelForm):
    class Meta:
        model = OrderLine
        fields = ['product','quantity','unit_price']
        widgets = {'quantity': forms.NumberInput(attrs={'min': 1}), 'unit_price': forms.NumberInput(attrs={'min': 0,'step':'0.01'})}
    def clean_quantity(self):
        value = self.cleaned_data['quantity']
        if value < 1: raise forms.ValidationError('Quantity must be at least one.')
        return value

class CycleCountForm(StyledModelForm):
    class Meta:
        model = CycleCount
        fields = ['product','location','counted_quantity','notes']
        widgets = {'counted_quantity': forms.NumberInput(attrs={'min':0})}

class ReturnRecordForm(StyledModelForm):
    class Meta:
        model = ReturnRecord
        fields = ['return_type','product','quantity','condition','reference','reason']
        widgets = {'quantity': forms.NumberInput(attrs={'min':1})}
    def clean_quantity(self):
        value = self.cleaned_data['quantity']
        if value < 1: raise forms.ValidationError('Quantity must be at least one.')
        return value

class ProductBatchForm(StyledModelForm):
    class Meta:
        model = ProductBatch
        fields = ['product','batch_number','quantity','received_date','expiry_date','quarantined']
        widgets = {'received_date': forms.DateInput(attrs={'type':'date'}), 'expiry_date': forms.DateInput(attrs={'type':'date'})}
>>>>>>> origin/main
