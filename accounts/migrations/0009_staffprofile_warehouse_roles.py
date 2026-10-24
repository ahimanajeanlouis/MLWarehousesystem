from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("accounts", "0008_extended_operations"),
    ]

    operations = [
        migrations.AlterField(
            model_name="staffprofile",
            name="role",
            field=models.CharField(
                choices=[
                    ("ADMIN", "Administrator"),
                    ("MANAGER", "Warehouse manager"),
                    ("RECEIVER", "Receiver"),
                    ("PUTAWAY", "Putaway operator"),
                    ("INVENTORY", "Inventory operator"),
                    ("PICKER", "Picker"),
                    ("PACKER", "Packer"),
                    ("SHIPPER", "Shipper"),
                    ("VIEWER", "Read-only viewer"),
                ],
                default="VIEWER",
                max_length=12,
            ),
        ),
    ]