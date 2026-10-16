from typing import Any, cast

from django.contrib.auth.models import User
from django.http import HttpRequest, HttpResponse
from django.views.decorators.csrf import csrf_exempt
from graphene_django.views import GraphQLView
from rest_framework.exceptions import AuthenticationFailed
from rest_framework_simplejwt.authentication import JWTAuthentication


class AnalyticsGraphQLView(GraphQLView):
    """GraphQL endpoint that accepts an admin session or a JWT `Bearer` token.

    The schema is read-only (queries only, no mutations), so exempting it from
    CSRF does not let a third-party page change any data.
    """

    def dispatch(self, request: HttpRequest, *args: Any, **kwargs: Any) -> HttpResponse:
        if request.headers.get('Authorization', '').startswith('Bearer '):
            try:
                result = JWTAuthentication().authenticate(request)  # type: ignore[arg-type]  # DRF expects its Request wrapper; it only reads headers
            except AuthenticationFailed:
                result = None
            if result is not None:
                request.user = cast(User, result[0])
        return super().dispatch(request, *args, **kwargs)


graphql_view = csrf_exempt(AnalyticsGraphQLView.as_view(graphiql=True))
