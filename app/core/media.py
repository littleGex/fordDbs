import json
import os
import subprocess

MAX_VIDEO_DURATION_SECONDS = 30
MAX_VIDEO_UPLOAD_BYTES = 150 * 1024 * 1024  # 150MB, DoS/hang guard on a Pi

VIDEO_EXTENSIONS = {"mp4", "mov", "m4v", "webm", "avi", "3gp", "mkv"}

_FFPROBE_TIMEOUT_SECONDS = 30
_FFMPEG_TIMEOUT_SECONDS = 300


class VideoProcessingError(Exception):
    """Raised when ffprobe/ffmpeg can't read or transcode an upload."""


def is_video_upload(file) -> bool:
    content_type = (file.content_type or "").lower()
    if content_type.startswith("video/"):
        return True
    ext = (file.filename or "").rsplit(".", 1)[-1].lower()
    return ext in VIDEO_EXTENSIONS


def probe_duration_seconds(path: str) -> float:
    try:
        result = subprocess.run(
            [
                "ffprobe", "-v", "error",
                "-show_entries", "format=duration",
                "-of", "json", path,
            ],
            capture_output=True, text=True,
            timeout=_FFPROBE_TIMEOUT_SECONDS,
        )
    except (subprocess.TimeoutExpired, OSError) as exc:
        raise VideoProcessingError(f"Could not read video file: {exc}")

    if result.returncode != 0:
        raise VideoProcessingError(
            f"Could not read video file: {result.stderr.strip()}")

    try:
        duration = json.loads(result.stdout)["format"]["duration"]
        return float(duration)
    except (KeyError, ValueError, json.JSONDecodeError) as exc:
        raise VideoProcessingError(f"Could not read video duration: {exc}")


def transcode_to_h264_mp4(input_path: str, output_path: str,
                          max_height: int = 720) -> None:
    try:
        result = subprocess.run(
            [
                "ffmpeg", "-y", "-i", input_path,
                "-vf", f"scale=-2:'min({max_height},ih)'",
                "-c:v", "libx264", "-preset", "veryfast", "-crf", "23",
                "-c:a", "aac", "-b:a", "128k",
                "-movflags", "+faststart",
                output_path,
            ],
            capture_output=True, text=True,
            timeout=_FFMPEG_TIMEOUT_SECONDS,
        )
    except (subprocess.TimeoutExpired, OSError) as exc:
        raise VideoProcessingError(f"Could not process video: {exc}")

    if result.returncode != 0:
        stderr_tail = "\n".join(result.stderr.strip().splitlines()[-15:])
        raise VideoProcessingError(f"Could not process video: {stderr_tail}")

    if not os.path.exists(output_path) or os.path.getsize(output_path) == 0:
        raise VideoProcessingError("Transcode produced no output")
