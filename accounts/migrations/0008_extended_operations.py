from datetime import date
import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models

class Migration(migrations.Migration):
    dependencies = [('accounts','0007_warehouse_controls'), migrations.swappable_dependency(settings.AUTH_USER_MODEL)]
    operations = [
        migrations.AddField(model_name='receiving', name='supplier_record', field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name='receipts', to='accounts.supplier')),
        migrations.AddField(model_name='receiving', name='batch_number', field=models.CharField(blank=True, max_length=80)),
        migrations.AddField(model_name='putaway', name='location_ref', field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name='putaways', to='accounts.warehouselocation')),
        migrations.AddField(model_name='shipping', name='carrier', field=models.CharField(blank=True, max_length=100)),
        migrations.AddField(model_name='shipping', name='tracking_number', field=models.CharField(blank=True, db_index=True, max_length=100)),
        migrations.AddField(model_name='shipping', name='proof_of_delivery', field=models.TextField(blank=True)),
        migrations.AddField(model_name='shipping', name='delivered_at', field=models.DateTimeField(blank=True, null=True)),
        migrations.CreateModel(name='Order', fields=[
            ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
            ('reference', models.CharField(max_length=50, unique=True)), ('shipping_address', models.TextField()), ('billing_address', models.TextField(blank=True)),
            ('status', models.CharField(choices=[('DRAFT','Draft'),('OPEN','Open'),('PARTIALLY_FULFILLED','Partially Fulfilled'),('FULFILLED','Fulfilled'),('CANCELLED','Cancelled')], default='OPEN', max_length=24)),
            ('notes', models.TextField(blank=True)), ('created_at', models.DateTimeField(auto_now_add=True)), ('updated_at', models.DateTimeField(auto_now=True)),
            ('created_by', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, to=settings.AUTH_USER_MODEL)),
            ('customer', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='orders', to='accounts.customer')),
        ]),
        migrations.CreateModel(name='OrderLine', fields=[
            ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
            ('quantity', models.PositiveIntegerField()), ('unit_price', models.DecimalField(decimal_places=2, default=0, max_digits=12)),
            ('order', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='lines', to='accounts.order')),
            ('product', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, to='accounts.product')),
        ]),
        migrations.CreateModel(name='CycleCount', fields=[
            ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
            ('expected_quantity', models.PositiveIntegerField()), ('counted_quantity', models.PositiveIntegerField()), ('notes', models.TextField(blank=True)),
            ('status', models.CharField(choices=[('OPEN','Open'),('RECONCILED','Reconciled'),('CANCELLED','Cancelled')], default='OPEN', max_length=12)),
            ('created_at', models.DateTimeField(auto_now_add=True)), ('reconciled_at', models.DateTimeField(blank=True, null=True)),
            ('counted_by', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='cycle_counts', to=settings.AUTH_USER_MODEL)),
            ('location', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, to='accounts.warehouselocation')),
            ('product', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, to='accounts.product')),
            ('reconciled_by', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name='cycle_counts_reconciled', to=settings.AUTH_USER_MODEL)),
        ]),
        migrations.CreateModel(name='ReturnRecord', fields=[
            ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
            ('return_type', models.CharField(choices=[('CUSTOMER','Customer return'),('SUPPLIER','Return to supplier')], max_length=10)),
            ('quantity', models.PositiveIntegerField()), ('condition', models.CharField(choices=[('GOOD','Good'),('DAMAGED','Damaged'),('EXPIRED','Expired')], max_length=10)),
            ('reference', models.CharField(max_length=80)), ('reason', models.TextField()),
            ('status', models.CharField(choices=[('PENDING','Pending inspection'),('RESTOCKED','Restocked'),('QUARANTINED','Quarantined'),('SENT','Sent to supplier'),('REJECTED','Rejected')], default='PENDING', max_length=12)),
            ('created_at', models.DateTimeField(auto_now_add=True)), ('reviewed_at', models.DateTimeField(blank=True, null=True)),
            ('created_by', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, to=settings.AUTH_USER_MODEL)),
            ('product', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, to='accounts.product')),
            ('reviewed_by', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name='returns_reviewed', to=settings.AUTH_USER_MODEL)),
        ]),
        migrations.CreateModel(name='ProductBatch', fields=[
            ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
            ('batch_number', models.CharField(max_length=80)), ('quantity', models.PositiveIntegerField(default=0)),
            ('received_date', models.DateField(default=date.today)), ('expiry_date', models.DateField(blank=True, null=True)), ('quarantined', models.BooleanField(default=False)),
            ('product', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='batches', to='accounts.product')),
        ], options={'ordering':['expiry_date','batch_number']}),
        migrations.AddConstraint(model_name='productbatch', constraint=models.UniqueConstraint(fields=('product','batch_number'), name='unique_product_batch')),
        migrations.CreateModel(name='StaffProfile', fields=[
            ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
            ('role', models.CharField(choices=[('ADMIN','Administrator'),('MANAGER','Warehouse manager'),('RECEIVER','Receiver'),('PICKER','Picker'),('PACKER','Packer'),('SHIPPER','Shipper'),('VIEWER','Read-only viewer')], default='VIEWER', max_length=12)),
            ('active', models.BooleanField(default=True)), ('user', models.OneToOneField(on_delete=django.db.models.deletion.CASCADE, related_name='staff_profile', to=settings.AUTH_USER_MODEL)),
        ]),
    ]
