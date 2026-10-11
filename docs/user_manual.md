# User Manual

## Start the application

1. From the repository root, start the FastAPI backend with
   `uv run uvicorn src.main:app --reload`.
2. In a second terminal, change to `frontend` and run `npm install` followed by
   `npm run dev`.
3. Open the local URL printed by Vite.

The frontend sends camera frames to the authenticated `POST /api/detect`
endpoint. Allow camera access in the browser and sign in before starting
detection. Warning and danger alerts are spoken in the browser when speech
synthesis is available. Frames may be JPEG, PNG, or WebP and must be 10 MiB or
smaller.

The selected alert language is saved in the browser. English uses browser
speech synthesis; most non-English alerts use the authenticated `/api/tts`
endpoint and Google Translate TTS. Tigrinya (`ti`), Oromo (`om`), and Somali
(`so`) use local MMS text-to-speech models because Google Translate TTS does
not support them. On first use, the selected model is downloaded and cached
locally, so the backend needs internet access and disk space for that download.
These three models are licensed CC-BY-NC 4.0 and are for non-commercial use
only. Persian (`fa`) is not supported by Google Translate TTS; the app will
report a clear error or use a matching browser voice when available.

YOLO inference uses Ultralytics and the `yolov8n.pt` model. The model may be
downloaded when the first frame is processed; set `YOLO_MODEL_PATH` to use a
local model file. The endpoint returns HTTP 503 if the inference dependencies
or model are unavailable. Distance values are estimates, not safety guarantees.
