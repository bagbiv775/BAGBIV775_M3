from django.contrib.auth.models import User
from django.core.exceptions import PermissionDenied
from django.http import HttpRequest


def authenticated_user(request: HttpRequest) -> User:
    """Return the logged-in user; views using it are already login-protected."""
    user = request.user
    if not isinstance(user, User):
        raise PermissionDenied
    return user
