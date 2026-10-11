function AlertBanner({ detections = [] }) {
  const urgentDetection = detections.find((detection) => detection.danger_level === 'danger');
  const warningDetection = detections.find((detection) => detection.danger_level === 'warning');
  const alert = urgentDetection || warningDetection;

  if (!alert) return null;

  const level = urgentDetection ? 'danger' : 'warning';
  const distance =
    alert.distance_m == null ? '' : `, ${alert.distance_m.toFixed(1)} m away`;

  return (
    <div className={`alert alert-${level}`} role="status" aria-live="polite">
      {level === 'danger' ? 'Danger' : 'Warning'}: {alert.label}
      {distance}
    </div>
  );
}

export default AlertBanner;
