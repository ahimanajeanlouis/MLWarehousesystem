from .permissions import modules_for_user


def role_access(request):
    if not request.user.is_authenticated:
        return {"accessible_modules": set()}
    return {"accessible_modules": modules_for_user(request.user)}