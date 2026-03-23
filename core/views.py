from django.shortcuts import  redirect
from .forms import CustomerForm

# Home page - list all customers
from django.shortcuts import render
from .models import Customer, WorkCode

def home(request):
    customers = Customer.objects.all().order_by('-created_at')
    workcodes = WorkCode.objects.all().order_by('code')

    return render(request, 'core/home.html', {
        'customers': customers,
        'workcodes': workcodes
    })


# Add new customer
def add_customer(request):
    if request.method == 'POST':
        form = CustomerForm(request.POST)
        if form.is_valid():
            form.save()
            return redirect('/')
    else:
        form = CustomerForm()

    return render(request, 'core/add_customer.html', {'form': form})