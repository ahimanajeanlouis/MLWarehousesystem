from django.db import migrations, models


def migrate_staff_roles(apps, schema_editor):
    StaffRole = apps.get_model('accounts', 'StaffRole')
    StaffProfile = apps.get_model('accounts', 'StaffProfile')
    labels = {
        'ADMIN': 'Administrator',
        'MANAGER': 'Warehouse manager',
        'RECEIVER': 'Receiver',
        'PUTAWAY': 'Putaway operator',
        'INVENTORY': 'Inventory operator',
        'PICKER': 'Picker',
        'PACKER': 'Packer',
        'SHIPPER': 'Shipper',
        'VIEWER': 'Read-only viewer',
    }
    role_objects = {
        code: StaffRole.objects.get_or_create(code=code, defaults={'name': name})[0]
        for code, name in labels.items()
    }
    for profile in StaffProfile.objects.all().iterator():
        old_role = getattr(profile, 'role', 'VIEWER')
        profile.roles.add(role_objects.get(old_role, role_objects['VIEWER']))


class Migration(migrations.Migration):
    dependencies = [('accounts', '0009_staffprofile_warehouse_roles')]

    operations = [
        migrations.CreateModel(
            name='StaffRole',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('code', models.CharField(choices=[('ADMIN','Administrator'),('MANAGER','Warehouse manager'),('RECEIVER','Receiver'),('PUTAWAY','Putaway operator'),('INVENTORY','Inventory operator'),('PICKER','Picker'),('PACKER','Packer'),('SHIPPER','Shipper'),('VIEWER','Read-only viewer')], max_length=12, unique=True)),
                ('name', models.CharField(max_length=50)),
            ],
            options={'ordering':['name']},
        ),
        migrations.AddField(model_name='staffprofile', name='roles', field=models.ManyToManyField(blank=True, related_name='staff_profiles', to='accounts.staffrole')),
        migrations.RunPython(migrate_staff_roles, migrations.RunPython.noop),
        migrations.RemoveField(model_name='staffprofile', name='role'),
    ]
