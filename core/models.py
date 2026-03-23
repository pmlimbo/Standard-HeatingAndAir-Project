# core/models.py
from django.db import models
class Customer(models.Model):
    name = models.CharField(max_length=100)
    email = models.EmailField()
    phone = models.CharField(max_length=20, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.name

# core/models.py
class JobType(models.Model):
    name = models.CharField(max_length=100)

    def __str__(self):
        return self.name


class WorkCode(models.Model):
    code = models.CharField(max_length=50)
    description = models.CharField(max_length=255, blank=True)

    def __str__(self):
        return f"{self.code} - {self.description}"