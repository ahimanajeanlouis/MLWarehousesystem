# =========================
# STAFF ROLES
# =========================
class StaffRole(models.Model):
    code = models.CharField(max_length=12, choices=[
        ('ADMIN', 'Administrator'),
        ('MANAGER', 'Warehouse manager'),
        ('RECEIVER', 'Receiver'),
        ('PUTAWAY', 'Putaway operator'),
        ('INVENTORY', 'Inventory operator'),
        ('PICKER', 'Picker'),
        ('PACKER', 'Packer'),
        ('SHIPPER', 'Shipper'),
        ('VIEWER', 'Read-only viewer'),
    ], unique=True)
    name = models.CharField(max_length=50)

    class Meta:
        ordering = ['name']

    def __str__(self):
        return self.name


class StaffProfile(models.Model):
    user = models.OneToOneField('auth.User', on_delete=models.CASCADE, related_name='staff_profile')
    roles = models.ManyToManyField(StaffRole, blank=True, related_name='staff_profiles')
    active = models.BooleanField(default=True)

    def __str__(self):
        role_names = ', '.join(self.roles.values_list('name', flat=True))
        return f'{self.user.username} — {role_names or "No role"}'
