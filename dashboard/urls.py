from __future__ import annotations

from django.urls import path

from . import views


urlpatterns = [
    path("health/", views.health, name="health"),
    path("outputs/", views.outputs, name="outputs"),
    path("run/", views.run_pipeline, name="run"),
    path("task/<str:task_id>/", views.task_status, name="task"),
    path("outputs/<str:folder>/<str:filename>", views.output_file, name="output-file"),
]

