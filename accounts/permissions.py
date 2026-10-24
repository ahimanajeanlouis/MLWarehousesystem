from functools import wraps

from django.http import HttpResponseForbidden


ROLE_MODULES = {
    "MANAGER": {"dashboard", "receiving", "putaway", "inventory", "picking", "packing", "shipping"},
    "RECEIVING": {"dashboard", "receiving"},
    "PUTAWAY": {"dashboard", "putaway"},
    "INVENTORY": {"dashboard", "inventory"},
    "PICKING": {"dashboard", "picking"},
    "PACKING": {"dashboard", "packing"},
    "SHIPPING": {"dashboard", "shipping"},
}


def modules_for_user(user):
    if user.is_superuser:
        return set(ROLE_MODULES["MANAGER"])

    try:
        role = user.role_profile.role
    except AttributeError:
        return set()

    return set(ROLE_MODULES.get(role, set()))


def module_required(module):
    def decorator(view):
        @wraps(view)
        def wrapped(request, *args, **kwargs):
            if module not in modules_for_user(request.user):
                return HttpResponseForbidden("Your role does not have access to this page.")
            return view(request, *args, **kwargs)

        return wrapped

    return decorator