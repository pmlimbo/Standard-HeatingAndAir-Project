from django import template

from core.views import is_authorized

register = template.Library()


@register.filter
def can_access_reports(user):
    if not getattr(user, 'is_authenticated', False):
        return False
    return is_authorized(user)
