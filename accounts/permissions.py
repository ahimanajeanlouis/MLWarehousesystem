from functools import wraps
from django.http import HttpResponseForbidden


ROLE_MODULES = {
    'ADMIN': {'dashboard','receiving','putaway','inventory','picking','packing','shipping','management'},
    'MANAGER': {'dashboard','receiving','putaway','inventory','picking','packing','shipping','management'},
    'RECEIVER': {'dashboard','receiving'},
    'PUTAWAY': {'dashboard','putaway'},
    'INVENTORY': {'dashboard','inventory'},
    'PICKER': {'dashboard','picking'},
    'PACKER': {'dashboard','packing'},
    'SHIPPER': {'dashboard','shipping'},
    'VIEWER': {'dashboard'},
}


def modules_for_user(user):
    if user.is_superuser or user.is_staff:
        return set(ROLE_MODULES['ADMIN'])
    profile = getattr(user, 'staff_profile', None)
    if profile is None or not profile.active:
        return set()
    modules = set()
    for code in profile.roles.values_list('code', flat=True):
        modules.update(ROLE_MODULES.get(code, set()))
    return modules


def module_required(module):
    def decorator(view):
        @wraps(view)
        def wrapped(request, *args, **kwargs):
            if module not in modules_for_user(request.user):
                return HttpResponseForbidden('Your role does not have access to this page.')
            return view(request, *args, **kwargs)
        return wrapped
    return decorator
