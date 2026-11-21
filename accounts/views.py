@login_required(login_url='login')
def staff_roles_page(request):
    if not _manager_required(request):
        messages.error(request, 'Only administrators and managers can manage staff roles.')
        return redirect('dashboard')
    if request.method == 'POST':
        user = get_object_or_404(User, pk=request.POST.get('user_id'))
        selected_codes = request.POST.getlist('roles')
        valid_codes = set(dict(StaffRole.choices if hasattr(StaffRole, 'choices') else []))
        role_queryset = StaffRole.objects.filter(code__in=selected_codes)
        if len(selected_codes) != role_queryset.count():
            messages.error(request, 'One or more selected roles are invalid.')
        else:
            profile, _ = StaffProfile.objects.get_or_create(user=user)
            profile.roles.set(role_queryset)
            profile.active = request.POST.get('active') == 'on'
            profile.save()
            _audit(request, 'ROLE_UPDATE', 'Staff', user.username, f'roles={",".join(selected_codes)}; active={profile.active}')
            messages.success(request, 'Staff roles updated.')
        return redirect('staff_roles')
    return render(request, 'accounts/staff_roles.html', {
        'users': User.objects.all().order_by('username'),
        'roles': StaffRole.objects.all().order_by('name'),
    })
