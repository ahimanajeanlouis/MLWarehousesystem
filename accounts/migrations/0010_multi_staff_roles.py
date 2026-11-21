from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("accounts", "0009_staffprofile_warehouse_roles"),
    ]

    operations = [
        migrations.CreateModel(
            name="StaffRole",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("code", models.CharField(choices=[("ADMIN", "Administrator"), ("MANAGER", "Warehouse manager"), ("RECEIVER", "Receiver"), ("PUTAWAY", "Putaway operator"), ("INVENTORY", "Inventory operator"), ("PICKER", "Picker"), ("PACKER", "Packer"), ("SHIPPER", "Shipper"), ("VIEWER", "Read-only viewer")], max_length=12, unique=True)),
                ("name", models.CharField(max_length=50)),
            ],
            options={"ordering": ["name"]},
        ),
        migrations.RemoveField(model_name="staffprofile", name="role"),
        migrations.AddField(
            model_name="staffprofile",
            name="roles",
            field=models.ManyToManyField(blank=True, related_name="staff_profiles", to="accounts.staffrole"),
        ),
        migrations.RunPython(migrate_staff_roles, migrations.RunPython.noop),
    ]


def migrate_staff_roles(apps, schema_editor):
    StaffRole = apps.get_model("accounts", "StaffRole")
    StaffProfile = apps.get_model("accounts", "StaffProfile")

    role_labels = {
        "ADMIN": "Administrator",
        "MANAGER": "Warehouse manager",
        "RECEIVER": "Receiver",
        "PUTAWAY": "Putaway operator",
        "INVENTORY": "Inventory operator",
        "PICKER": "Picker",
        "PACKER": "Packer",
        "SHIPPER": "Shipper",
        "VIEWER": "Read-only viewer",
    }

    roles = {}
    for code, name in role_labels.items():
        roles[code], _ = StaffRole.objects.get_or_create(code=code, defaults={"name": name})

    for profile in StaffProfile.objects.all():
        profile.roles.clear()
        profile.roles.add(roles.get("VIEWER") if not profile.roles.exists() else roles.get("VIEWER"))
