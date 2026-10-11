import { useEffect, useRef, useState } from 'react';
import { detectFrame } from '../services/api.js';

const INTERVAL_MS = 500;
const COLORS = { danger: '#ef4444', warning: '#f59e0b', safe: '#22c55e' };

export default function CameraFeed({ running, language = 'en', onResult, onError }) {
  const videoRef = useRef(null);
  const overlayRef = useRef(null);
  const captureRef = useRef(null);
  const busyRef = useRef(false);
  const pollingStoppedRef = useRef(false);
  const [cameraError, setCameraError] = useState('');
  const [cameraReady, setCameraReady] = useState(false);
  const [pageVisible, setPageVisible] = useState(() => !document.hidden);

  useEffect(() => {
    const updateVisibility = () => setPageVisible(!document.hidden);
    document.addEventListener('visibilitychange', updateVisibility);
    return () => document.removeEventListener('visibilitychange', updateVisibility);
  }, []);

  useEffect(() => {
    if (!running || !pageVisible) return undefined;
    if (!navigator.mediaDevices?.getUserMedia) {
      onError?.('Camera access requires HTTPS or localhost in a supported browser.');
      return undefined;
    }

    let stream;
    let cancelled = false;
    let releaseCameraLock;
    const video = videoRef.current;
    setCameraError('');

    const startCamera = async () => {
      setCameraReady(false);
      const cameraStream = await navigator.mediaDevices.getUserMedia({
        video: { width: { ideal: 640 }, height: { ideal: 480 } },
        audio: false,
      });
      if (cancelled) {
        cameraStream.getTracks().forEach((track) => track.stop());
        return;
      }
      stream = cameraStream;
      setCameraError('');
      if (video) {
        video.srcObject = cameraStream;
        await video.play();
        setCameraReady(video.readyState >= 2);
      }
    };

    const requestCamera = async () => {
      if (navigator.locks?.request) {
        await navigator.locks.request(
          'ai-obstacle-detection-camera',
          { ifAvailable: true },
          async (lock) => {
            if (!lock) {
              throw new DOMException(
                'Another dashboard tab is already using the camera.',
                'CameraTabInUseError',
              );
            }
            await startCamera();
            await new Promise((resolve) => {
              releaseCameraLock = resolve;
              if (cancelled) resolve();
            });
          },
        );
      } else {
        await startCamera();
      }
    };

    requestCamera().catch((error) => {
      if (cancelled) return;
      stream?.getTracks().forEach((track) => track.stop());
      stream = undefined;
      if (video) video.srcObject = null;
      const message = getCameraErrorMessage(error);
      setCameraError(message);
      onError?.(message);
    });

    return () => {
      cancelled = true;
      releaseCameraLock?.();
      stream?.getTracks().forEach((track) => track.stop());
      if (video) video.srcObject = null;
      setCameraReady(false);
    };
  }, [running, pageVisible, onError]);

  useEffect(() => {
    if (!running || !pageVisible) return undefined;
    pollingStoppedRef.current = false;

    let timer;
    let started = false;
    const detectCurrentFrame = async () => {
      const video = videoRef.current;
      if (
        pollingStoppedRef.current ||
        !video ||
        video.readyState < 2 ||
        busyRef.current
      ) {
        return;
      }

      busyRef.current = true;
      try {
        const canvas = captureRef.current ?? document.createElement('canvas');
        captureRef.current = canvas;
        canvas.width = video.videoWidth;
        canvas.height = video.videoHeight;

        const context = canvas.getContext('2d');
        if (!context) throw new Error('Could not prepare a camera frame.');
        context.drawImage(video, 0, 0);

        const blob = await new Promise((resolve) => canvas.toBlob(resolve, 'image/jpeg', 0.7));
        if (!blob) throw new Error('Could not capture a camera frame.');

        const result = await detectFrame(blob, language);
        drawBoxes(overlayRef.current, video, result);
        onResult?.(result);
      } catch (error) {
        pollingStoppedRef.current = true;
        onError?.(error.message || 'Frame detection failed.');
      } finally {
        busyRef.current = false;
      }
    };

    const startPolling = () => {
      if (started || pollingStoppedRef.current) return;
      started = true;
      void detectCurrentFrame();
      timer = window.setInterval(() => {
        void detectCurrentFrame();
      }, INTERVAL_MS);
    };

    const video = videoRef.current;
    if (video?.readyState >= 2) {
      startPolling();
    } else {
      video?.addEventListener('loadeddata', startPolling, { once: true });
    }

    return () => {
      pollingStoppedRef.current = true;
      window.clearInterval(timer);
      video?.removeEventListener('loadeddata', startPolling);
    };
  }, [running, pageVisible, language, onResult, onError]);

  const cameraStatus = cameraReady ? 'Detecting live…' : 'Starting camera…';

  return (
    <div style={{ position: 'relative', width: '100%', height: '100%' }}>
      <video
        ref={videoRef}
        aria-label="Live camera feed"
        autoPlay
        playsInline
        muted
        style={{ width: '100%', height: '100%', objectFit: 'cover' }}
      />
      {running && !cameraError && (
        <span
          role="status"
          style={{
            position: 'absolute',
            top: 12,
            left: 12,
            padding: '0.4rem 0.65rem',
            borderRadius: 8,
            color: '#fff',
            background: 'rgba(0,0,0,0.65)',
            fontSize: '0.85rem',
          }}
        >
          {cameraStatus}
        </span>
      )}
      <canvas
        ref={overlayRef}
        aria-hidden="true"
        style={{
          position: 'absolute',
          top: 0,
          left: 0,
          width: '100%',
          height: '100%',
          pointerEvents: 'none',
        }}
      />
      {!running && (
        <div
          style={{
            position: 'absolute',
            inset: 0,
            display: 'grid',
            placeItems: 'center',
            color: '#94a3b8',
          }}
        >
          Press Start to begin detection
        </div>
      )}
      {cameraError && running && (
        <div
          role="alert"
          style={{
            position: 'absolute',
            inset: 0,
            display: 'grid',
            placeItems: 'center',
            color: '#fca5a5',
            background: 'rgba(0,0,0,0.7)',
          }}
        >
          {cameraError}
        </div>
      )}
    </div>
  );
}

function getCameraErrorMessage(error) {
  switch (error?.name) {
    case 'CameraTabInUseError':
      return 'Another dashboard tab is using the camera. Switch to that tab or close it, then try again.';
    case 'NotAllowedError':
    case 'PermissionDeniedError':
      return 'Camera permission was denied. Allow camera access for this site in your browser, then check Windows camera privacy settings.';
    case 'NotFoundError':
    case 'DevicesNotFoundError':
      return 'No camera was found. Connect or enable a camera, then press Start Detection again.';
    case 'NotReadableError':
    case 'TrackStartError':
      return 'The camera is busy in another tab or app. Close other apps using it, then press Start Detection again.';
    case 'OverconstrainedError':
      return 'The camera does not support the requested video settings.';
    case 'SecurityError':
      return 'The browser blocked camera access. Open this app on localhost or over HTTPS.';
    default:
      return `Could not start the camera${error?.name ? ` (${error.name})` : ''}. Check browser and Windows camera permissions, then try again.`;
  }
}

function drawBoxes(canvas, video, result) {
  if (!canvas || !result?.width || !result?.height) return;

  canvas.width = video.clientWidth;
  canvas.height = video.clientHeight;
  const context = canvas.getContext('2d');
  if (!context) return;

  context.clearRect(0, 0, canvas.width, canvas.height);
  const scaleX = canvas.width / result.width;
  const scaleY = canvas.height / result.height;
  context.lineWidth = 3;
  context.font = '14px sans-serif';

  for (const detection of result.detections || []) {
    if (!Array.isArray(detection.bbox) || detection.bbox.length !== 4) continue;
    const [x1, y1, x2, y2] = detection.bbox;
    const color = COLORS[detection.danger_level] || COLORS.safe;
    const left = x1 * scaleX;
    const top = y1 * scaleY;
    const label = `${detection.label} ${detection.distance_m ?? '?'}m`;
    const labelWidth = context.measureText(label).width + 8;

    context.strokeStyle = color;
    context.strokeRect(left, top, (x2 - x1) * scaleX, (y2 - y1) * scaleY);
    context.fillStyle = color;
    context.fillRect(left, Math.max(0, top - 20), labelWidth, 20);
    context.fillStyle = '#fff';
    context.fillText(label, left + 4, Math.max(14, top - 5));
  }
}
