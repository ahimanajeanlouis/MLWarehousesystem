from functools import wraps

from django.http import HttpResponseForbidden


ROLE_MODULES = {
    "ADMIN": {"dashboard", "receiving", "putaway", "inventory", "picking", "packing", "shipping", "management"},
    "MANAGER": {"dashboard", "receiving", "putaway", "inventory", "picking", "packing", "shipping", "management"},
    "RECEIVER": {"dashboard", "receiving"},
    "PUTAWAY": {"dashboard", "putaway"},
    "INVENTORY": {"dashboard", "inventory"},
    "PICKER": {"dashboard", "picking"},
    "PACKER": {"dashboard", "packing"},
    "SHIPPER": {"dashboard", "shipping"},
    "VIEWER": {"dashboard"},
}


def modules_for_user(user):
    if user.is_superuser:
        return set(ROLE_MODULES["ADMIN"])

    try:
        profile = user.staff_profile
    except AttributeError:
        return set()

    if not profile.active:
        return set()
    return set(ROLE_MODULES.get(profile.role, set()))


def module_required(module):
    def decorator(view):
        @wraps(view)
        def wrapped(request, *args, **kwargs):
            if module not in modules_for_user(request.user):
                return HttpResponseForbidden("Your role does not have access to this page.")
            return view(request, *args, **kwargs)

        return wrapped

    return decorator