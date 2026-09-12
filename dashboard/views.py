from __future__ import annotations

import json
from pathlib import Path

from django.http import (
    FileResponse,
    Http404,
    HttpRequest,
    HttpResponse,
    JsonResponse,
    StreamingHttpResponse,
)
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
    skip_youtube = bool(payload.get("skip_youtube", False))
    skip_instagram = bool(payload.get("skip_instagram", False))
    run_date = payload.get("run_date")
    if isinstance(run_date, str):
        run_date = run_date.strip() or None

    task_id = services.start_pipeline_task(
        skip_upload=skip_upload,
        skip_youtube=skip_youtube,
        skip_instagram=skip_instagram,
        run_date=run_date,
    )
    return JsonResponse({"status": "started", "task_id": task_id})


def task_status(request: HttpRequest, task_id: str) -> JsonResponse:
    if request.method != "GET":
        return JsonResponse({"error": "method tidak diizinkan"}, status=405)
    task = services.get_task(task_id)
    if task is None:
        return JsonResponse({"error": "task tidak ditemukan"}, status=404)
    return JsonResponse(task)


_CONTENT_TYPES = {
    ".mp4": "video/mp4",
    ".mp3": "audio/mpeg",
    ".png": "image/png",
    ".json": "application/json",
    ".txt": "text/plain; charset=utf-8",
}
# Hanya media yang mendukung byte-range (seek di player).
_MEDIA_SUFFIXES = {".mp4", ".mp3"}
# File yang ditampilkan langsung di halaman, bukan diunduh.
_INLINE_SUFFIXES = _MEDIA_SUFFIXES | {".png"}
_STREAM_CHUNK = 512 * 1024


def _parse_byte_range(header: str, size: int) -> tuple[int, int] | None:
    """Parse the first range of a `bytes=` header. None berarti tidak memenuhi syarat."""
    spec = header[len("bytes=") :].split(",", 1)[0].strip()
    first, sep, last = spec.partition("-")
    if not sep:
        return None
    try:
        if not first:  # suffix range, contoh: bytes=-500
            length = int(last)
            if length <= 0:
                return None
            start = max(0, size - length)
            end = size - 1
        else:
            start = int(first)
            end = int(last) if last else size - 1
    except ValueError:
        return None
    if start >= size or end < start:
        return None
    return start, min(end, size - 1)


def _file_chunks(path: Path, start: int, length: int):
    with path.open("rb") as handle:
        handle.seek(start)
        remaining = length
        while remaining > 0:
            chunk = handle.read(min(_STREAM_CHUNK, remaining))
            if not chunk:
                break
            remaining -= len(chunk)
            yield chunk


def output_file(request: HttpRequest, folder: str, filename: str) -> HttpResponse:
    if request.method != "GET":
        raise Http404("method tidak diizinkan")

    path = services.resolve_output_file(folder, filename)
    if path is None:
        raise Http404("file tidak ditemukan")

    suffix = path.suffix.lower()
    content_type = _CONTENT_TYPES.get(suffix, "application/octet-stream")
    is_media = suffix in _MEDIA_SUFFIXES
    size = path.stat().st_size

    range_header = request.headers.get("Range", "") if is_media else ""
    if range_header.startswith("bytes="):
        byte_range = _parse_byte_range(range_header, size)
        if byte_range is None:
            response = HttpResponse(status=416)
            response["Content-Range"] = f"bytes */{size}"
            response["Accept-Ranges"] = "bytes"
            return response
        start, end = byte_range
        length = end - start + 1
        partial = StreamingHttpResponse(
            _file_chunks(path, start, length), status=206, content_type=content_type
        )
        partial["Content-Range"] = f"bytes {start}-{end}/{size}"
        partial["Content-Length"] = str(length)
        partial["Accept-Ranges"] = "bytes"
        return partial

    response = FileResponse(
        path.open("rb"),
        as_attachment=suffix not in _INLINE_SUFFIXES,
        filename=path.name,
        content_type=content_type,
    )
    if is_media:
        response["Accept-Ranges"] = "bytes"
    return response
