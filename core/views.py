from django.shortcuts import  redirect
from .forms import CustomerForm

# Home page - list all customers
from django.shortcuts import render
from .models import Customer, WorkCode

from django.contrib.auth.decorators import login_required
from django.contrib.auth.decorators import user_passes_test

#authorization
def is_authorized(user):
    return (
        user.is_superuser or
        user.is_staff or
        user.groups.filter(name='Authorized').exists()
    )

#home page
@login_required
def home(request):
    customers = Customer.objects.all().order_by('-created_at')
    workcodes = WorkCode.objects.all().order_by('code')

    return render(request, 'core/home.html', {
        'customers': customers,
        'workcodes': workcodes
    })


# Add new customer
@login_required
def add_customer(request):
    if request.method == 'POST':
        form = CustomerForm(request.POST)
        if form.is_valid():
            form.save()
            return redirect('/')
    else:
        form = CustomerForm()

    return render(request, 'core/add_customer.html', {'form': form})

@login_required
@user_passes_test(is_authorized, login_url='/')
def reports(request):
    return render(request, 'core/reports.html')

