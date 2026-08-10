from __future__ import annotations

import json
from pathlib import Path

from django.http import FileResponse, Http404, HttpRequest, HttpResponse, JsonResponse
from django.views.decorators.csrf import csrf_exempt

from . import services


def health(request: HttpRequest) -> JsonResponse:
    return JsonResponse({"status": "ok", "service": "dashboard-api"})


def outputs(request: HttpRequest) -> JsonResponse:
    if request.method != "GET":
        return JsonResponse({"error": "method tidak diizinkan"}, status=405)
    return JsonResponse(
        {
            "outputs": services.get_outputs(),
            "recent_tasks": services.get_tasks(limit=10),
        }
    )


@csrf_exempt
def run_pipeline(request: HttpRequest) -> JsonResponse:
    if request.method != "POST":
        return JsonResponse({"error": "method tidak diizinkan"}, status=405)

    payload: dict = {}
    if request.body:
        try:
            payload = json.loads(request.body.decode("utf-8"))
        except json.JSONDecodeError:
            return JsonResponse({"error": "payload json tidak valid"}, status=400)

    skip_upload = bool(payload.get("skip_upload", False))
    run_date = payload.get("run_date")
    if isinstance(run_date, str):
        run_date = run_date.strip() or None

    task_id = services.start_pipeline_task(skip_upload=skip_upload, run_date=run_date)
    return JsonResponse({"status": "started", "task_id": task_id})


def task_status(request: HttpRequest, task_id: str) -> JsonResponse:
    if request.method != "GET":
        return JsonResponse({"error": "method tidak diizinkan"}, status=405)
    task = services.get_task(task_id)
    if task is None:
        return JsonResponse({"error": "task tidak ditemukan"}, status=404)
    return JsonResponse(task)


def output_file(request: HttpRequest, folder: str, filename: str) -> FileResponse:
    if request.method != "GET":
        raise Http404("method tidak diizinkan")

    if filename not in {"script.json", "voiceover.mp3", "final_video.mp4", "thumbnail.png", "ig_caption.txt"}:
        raise Http404("file tidak diizinkan")

    path = Path("output") / folder / filename
    if not path.exists() or not path.is_file():
        raise Http404("file tidak ditemukan")

    as_attachment = not filename.endswith(".mp4")
    return FileResponse(path.open("rb"), as_attachment=as_attachment, filename=path.name)
