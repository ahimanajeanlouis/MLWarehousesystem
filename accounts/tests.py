from django.contrib.auth.models import User
from django.db.models import Sum
from django.test import TestCase

from .models import Packing, Picking, Product, Putaway, Receiving, Shipping, StaffProfile, StaffRole


class ReceivingPutawayInventoryTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="warehouse-user", password="test-password")
        self.assign_role(self.user, "MANAGER")
        self.client.force_login(self.user)

    def assign_role(self, user, code):
        labels = dict(StaffRole._meta.get_field("code").choices)
        role, _ = StaffRole.objects.get_or_create(code=code, defaults={"name": labels[code]})
        profile = StaffProfile.objects.create(user=user)
        profile.roles.add(role)

    def receive_goods(self, **overrides):
        data = {
            "product_name": "Pallet Jack",
            "sku": "PJ-100",
            "quantity": 4,
            "unit_price": "25.00",
            "supplier": "Warehouse Supplier",
            "condition": Receiving.CONDITION_GOOD,
        }
        data.update(overrides)
        return self.client.post("/receiving/", data)

    def test_good_receiving_updates_inventory_only_after_putaway(self):
        response = self.receive_goods()

        self.assertRedirects(response, "/receiving/")
        receiving = Receiving.objects.get(sku="PJ-100")
        self.assertFalse(Product.objects.filter(sku="PJ-100").exists())

        putaway_response = self.client.post(
            "/putaway/",
            {"receiving": receiving.pk, "location": "A-01"},
        )

        self.assertRedirects(putaway_response, "/putaway/")
        receiving.refresh_from_db()
        product = Product.objects.get(sku="PJ-100")
        self.assertEqual(product.name, "Pallet Jack")
        self.assertEqual(product.quantity, 4)
        self.assertEqual(receiving.status, "STORED")
        self.assertTrue(receiving.inventory_updated)
        self.assertTrue(Putaway.objects.filter(receiving=receiving).exists())

    def test_putaway_choices_only_include_good_received_goods(self):
        good_receiving = Receiving.objects.create(
            product_name="Pallet Jack",
            sku="PJ-100",
            quantity=4,
            unit_price="25.00",
            supplier="Warehouse Supplier",
        )
        damaged_receiving = Receiving.objects.create(
            product_name="Damaged Pallet Jack",
            sku="PJ-200",
            quantity=2,
            unit_price="25.00",
            supplier="Warehouse Supplier",
            condition=Receiving.CONDITION_DAMAGED,
        )

        response = self.client.get("/putaway/")

        self.assertContains(response, "Pallet Jack — SKU PJ-100 — Qty 4")
        self.assertNotContains(response, "Damaged Pallet Jack")
        self.assertIn(good_receiving, response.context["form"].fields["receiving"].queryset)
        self.assertNotIn(damaged_receiving, response.context["form"].fields["receiving"].queryset)

    def test_inventory_page_has_no_manual_product_entry_form(self):
        response = self.client.get("/inventory/")

        self.assertContains(response, "All Products")
        self.assertNotContains(response, "Add New Product")
        self.assertNotContains(response, "Save Product")

    def test_picking_selects_inventory_product_and_uses_its_name_and_sku(self):
        product = Product.objects.create(
            name="Pallet Jack",
            sku="PJ-100",
            quantity=8,
        )
        out_of_stock = Product.objects.create(
            name="Empty Pallet Jack",
            sku="PJ-000",
            quantity=0,
        )

        response = self.client.get("/picking/")

        self.assertContains(response, "Pallet Jack — SKU PJ-100 — Available: 8")
        self.assertNotContains(response, "Empty Pallet Jack")
        self.assertIn(product, response.context["form"].fields["product"].queryset)
        self.assertNotIn(out_of_stock, response.context["form"].fields["product"].queryset)

        post_response = self.client.post(
            "/picking/",
            {"product": product.pk, "quantity": 3, "order_reference": "ORD-2001"},
        )

        self.assertRedirects(post_response, "/picking/")
        product.refresh_from_db()
        picking = Picking.objects.get(order_reference="ORD-2001")
        self.assertEqual(picking.product_name, "Pallet Jack")
        self.assertEqual(picking.sku, "PJ-100")
        self.assertEqual(picking.quantity, 3)
        self.assertEqual(product.quantity, 5)

    def test_picking_rejects_product_not_in_inventory_choices(self):
        product = Product.objects.create(
            name="Pallet Jack",
            sku="PJ-100",
            quantity=0,
        )

        response = self.client.post(
            "/picking/",
            {"product": product.pk, "quantity": 1, "order_reference": "ORD-2002"},
        )

        self.assertEqual(response.status_code, 200)
        self.assertFalse(Picking.objects.filter(order_reference="ORD-2002").exists())

    def test_packing_choices_only_include_picked_products_with_remaining_quantity(self):
        product = Product.objects.create(name="Pallet Jack", sku="PJ-100", quantity=5)
        other_product = Product.objects.create(name="Forklift", sku="FL-200", quantity=5)
        Picking.objects.create(
            product_name=product.name,
            sku=product.sku,
            quantity=5,
            order_reference="ORD-3001",
        )
        Picking.objects.create(
            product_name=other_product.name,
            sku=other_product.sku,
            quantity=2,
            order_reference="ORD-3002",
        )
        Packing.objects.create(order_ref="ORD-3001", product=product, quantity=3)

        response = self.client.get("/packing/")
        form = response.context["form"]

        self.assertEqual(
            form.fields["order_ref"].choices[1:],
            [("ORD-3001", "ORD-3001"), ("ORD-3002", "ORD-3002")],
        )
        self.assertEqual(list(form.fields["product"].queryset), [])

        response = self.client.get("/packing/?order_ref=ORD-3001")
        form = response.context["form"]
        self.assertEqual(list(form.fields["product"].queryset), [product])
        self.assertContains(response, "Remaining to pack: 2")

        response = self.client.post(
            "/packing/",
            {"order_ref": "ORD-3001", "product": product.pk, "quantity": 2},
        )

        self.assertRedirects(response, "/packing/")
        self.assertEqual(Packing.objects.filter(order_ref="ORD-3001").aggregate(total=Sum("quantity"))["total"], 5)

    def test_shipping_choices_only_include_packed_products_with_remaining_quantity(self):
        product = Product.objects.create(name="Pallet Jack", sku="PJ-100", quantity=0)
        Packing.objects.create(order_ref="ORD-4001", product=product, quantity=4)
        Shipping.objects.create(
            order_ref="ORD-4001",
            product=product,
            quantity=1,
            destination="Customer",
        )

        response = self.client.get("/shipping/?order_ref=ORD-4001")
        form = response.context["form"]
        self.assertEqual(list(form.fields["product"].queryset), [product])
        self.assertContains(response, "Remaining to ship: 3")

        response = self.client.post(
            "/shipping/",
            {
                "order_ref": "ORD-4001",
                "product": product.pk,
                "quantity": 3,
                "destination": "Customer",
            },
        )

        self.assertRedirects(response, "/shipping/")
        self.assertEqual(Shipping.objects.filter(order_ref="ORD-4001").aggregate(total=Sum("quantity"))["total"], 4)
class RoleAccessTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="receiving-user", password="test-password")
        labels = dict(StaffRole._meta.get_field("code").choices)
        role, _ = StaffRole.objects.get_or_create(code="RECEIVER", defaults={"name": labels["RECEIVER"]})
        profile = StaffProfile.objects.create(user=self.user)
        profile.roles.add(role)
        self.client.force_login(self.user)

    def test_role_can_access_its_module_and_dashboard(self):
        dashboard_response = self.client.get("/dashboard/")
        self.assertEqual(dashboard_response.status_code, 200)
        self.assertTemplateUsed(dashboard_response, "accounts/role_dashboard.html")
        self.assertContains(dashboard_response, "Receiving Dashboard")
        response = self.client.get("/receiving/")
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Receiving")

    def test_role_cannot_access_other_module_by_direct_url(self):
        response = self.client.get("/inventory/")

        self.assertEqual(response.status_code, 403)

    def test_dashboard_only_displays_permitted_module(self):
        response = self.client.get("/dashboard/")

        self.assertContains(response, "Receiving")
        self.assertNotContains(response, "Inventory")
        self.assertNotContains(response, "Picking")
        self.assertContains(response, 'name="period"')
        self.assertContains(response, 'value="daily"')
        self.assertContains(response, 'value="weekly"')
        self.assertContains(response, 'value="monthly"')

    def test_picker_sees_only_the_picking_dashboard_and_module(self):
        user = User.objects.create_user(username="picker-user", password="test-password")
        labels = dict(StaffRole._meta.get_field("code").choices)
        role, _ = StaffRole.objects.get_or_create(
            code="PICKER", defaults={"name": labels["PICKER"]}
        )
        StaffProfile.objects.create(user=user).roles.add(role)
        self.client.force_login(user)

        response = self.client.get("/dashboard/")

        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "accounts/role_dashboard.html")
        self.assertContains(response, "Picking Dashboard")
        self.assertContains(response, "Picking tasks recorded")
        self.assertNotContains(response, "Receiving")
        self.assertNotContains(response, "Inventory")

    def test_manager_can_assign_picker_role_and_employee_gets_picking_dashboard(self):
        manager = User.objects.create_user(username="role-manager", password="test-password")
        labels = dict(StaffRole._meta.get_field("code").choices)
        manager_role, _ = StaffRole.objects.get_or_create(
            code="MANAGER", defaults={"name": labels["MANAGER"]}
        )
        StaffProfile.objects.create(user=manager).roles.add(manager_role)
        employee = User.objects.create_user(username="assigned-picker", password="test-password")
        self.client.force_login(manager)

        response = self.client.post(
            "/staff-roles/",
            {"user_id": employee.pk, "roles": ["PICKER"], "active": "on"},
        )

        self.assertRedirects(response, "/staff-roles/")
        self.client.force_login(employee)
        dashboard_response = self.client.get("/dashboard/")
        self.assertContains(dashboard_response, "Picking Dashboard")
        self.assertNotContains(dashboard_response, "Receiving")

    def test_manager_dashboard_shows_live_stock_and_employee_metrics(self):
        manager = User.objects.create_user(username="warehouse-manager", password="test-password")
        labels = dict(StaffRole._meta.get_field("code").choices)
        role, _ = StaffRole.objects.get_or_create(
            code="MANAGER", defaults={"name": labels["MANAGER"]}
        )
        profile = StaffProfile.objects.create(user=manager)
        profile.roles.add(role)
        self.client.force_login(manager)

        Product.objects.create(name="Available", sku="SKU-AVAILABLE", quantity=8, reorder_level=5)
        Product.objects.create(name="Low stock", sku="SKU-LOW", quantity=2, reorder_level=5)
        Product.objects.create(name="Out of stock", sku="SKU-OUT", quantity=0, reorder_level=5)

        response = self.client.get("/dashboard/")

        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "accounts/manager_dashboard.html")
        self.assertContains(response, "Manager Dashboard")
        self.assertEqual(response.context["employee_count"], 2)
        self.assertEqual(response.context["active_employee_count"], 2)
        self.assertEqual(response.context["product_count"], 3)
        self.assertEqual(response.context["product_units"], 10)
        self.assertEqual(response.context["low_stock_count"], 1)
        self.assertEqual(response.context["in_stock_count"], 1)
        self.assertEqual(response.context["out_of_stock_count"], 1)

    def test_manager_dashboard_rejects_unsupported_activity_period(self):
        manager = User.objects.create_user(username="period-manager", password="test-password")
        labels = dict(StaffRole._meta.get_field("code").choices)
        role, _ = StaffRole.objects.get_or_create(
            code="MANAGER", defaults={"name": labels["MANAGER"]}
        )
        StaffProfile.objects.create(user=manager).roles.add(role)
        self.client.force_login(manager)

        self.assertEqual(self.client.get("/dashboard/?period=365").status_code, 400)

    def test_unassigned_user_cannot_access_dashboard(self):
        user = User.objects.create_user(username="unassigned", password="test-password")
        self.client.force_login(user)

        self.assertEqual(self.client.get("/dashboard/").status_code, 403)

    def test_user_can_download_role_scoped_pdf_report(self):
        response = self.client.get("/reports/download/?period=daily")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Type"], "application/pdf")
        self.assertIn("attachment;", response["Content-Disposition"])
        self.assertTrue(response.content.startswith(b"%PDF"))

    def test_report_download_requires_valid_period(self):
        self.assertEqual(self.client.get("/reports/download/").status_code, 400)
        self.assertEqual(self.client.get("/reports/download/?period=yearly").status_code, 400)

    def test_all_supported_report_periods_download_as_pdf(self):
        for period in ("daily", "weekly", "monthly"):
            with self.subTest(period=period):
                response = self.client.get(f"/reports/download/?period={period}")
                self.assertEqual(response.status_code, 200)
                self.assertTrue(response.content.startswith(b"%PDF"))
