from django.urls import path
from . import views

urlpatterns = [
    path('', views.home),

    path('add/', views.add_customer),

    path('reports/', views.reports),
]