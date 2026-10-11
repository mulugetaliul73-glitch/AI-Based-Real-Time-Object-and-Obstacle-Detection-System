# AI Obstacle Detection

FastAPI backend and React frontend for an AI-assisted obstacle detection
application.

## Python version

This project requires **Python 3.14 or newer**. The configured environment is
Python **3.14.8**. The version is pinned to the 3.14 series in `.python-version`
and declared in `pyproject.toml`.

Check the active project interpreter with:

```powershell
uv run python --version
```

## Project layout

```text
.
├── docs/
│   └── user_manual.md
├── frontend/
│   └── src/
│       ├── components/
│       └── services/
├── models/                 # Put downloaded model weights here
├── src/
│   ├── ai/
│   ├── __init__.py
│   ├── auth.py
│   ├── crud.py
│   ├── database.py
│   ├── main.py
│   ├── models.py
│   └── schemas.py
└── tests/
```

Local secrets belong in `.env` and are ignored by Git. Do not commit `.env`,
virtual environments, frontend dependencies/build output, or downloaded model
weights. Add real model and report assets only when they are available.

## Run locally

Install the locked Python dependencies from the repository root:

```powershell
uv sync --locked
```

Then start the backend:

```powershell
uv run uvicorn src.main:app --reload
```

In another terminal, start the frontend:

```powershell
cd frontend
npm install
npm run dev
```

The frontend uses the FastAPI backend at `http://127.0.0.1:8000`. Create an
account or sign in to access the protected detection history and statistics.

Authentication endpoints:

- `POST /api/auth/register`
- `POST /api/auth/login`
- `GET /api/auth/me`

Detection endpoints require a bearer token:

- `POST /api/detect` to upload a JPEG, PNG, or WebP camera frame for YOLO
  detection (maximum 10 MiB); warning and danger results are saved to that
  user's history
- `GET /api/battery` to return the backend host's battery status
- `GET /api/location/reverse?latitude=...&longitude=...&language=...` to look up
  a human-readable OpenStreetMap place name when the user requests their
  location; this requires an internet connection and may return coordinates
  only when the map provider has no address for that area
- `POST /api/location/from-image` to extract GPS coordinates from an uploaded
  JPEG, PNG, or WebP image's EXIF metadata (maximum 10 MiB); images without GPS
  metadata return HTTP 404
- `POST /api/detections` to save one detection
- `POST /api/detections/batch` to save a batch, excluding `safe` detections
- `GET /api/detections` to list history, optionally filtered by `danger_level`
- `GET /api/detections/stats` to retrieve per-user counts
- `DELETE /api/detections` to clear the current user's history

The first detection request loads the Ultralytics `yolov8n.pt` model and may
download its weights. Set `YOLO_MODEL_PATH` to use a local model file instead.
If the model or inference dependencies are unavailable, the endpoint returns
HTTP 503; it does not return fabricated detections. Distance estimates are
approximate and should not be used as the sole basis for safety decisions.
