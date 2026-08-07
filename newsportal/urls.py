from __future__ import annotations

from django.http import JsonResponse
from django.urls import include, path


def root_health(_request):
    return JsonResponse({"ok": True, "service": "newsportal"})


urlpatterns = [
    path("api/", include("dashboard.urls")),
    path("", root_health, name="root-health"),
]

