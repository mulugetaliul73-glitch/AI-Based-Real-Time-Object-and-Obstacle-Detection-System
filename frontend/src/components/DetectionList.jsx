function DetectionList({ detections = [] }) {
  if (detections.length === 0) {
    return <p>No objects detected.</p>;
  }

  return (
    <ul>
      {detections.map((detection, index) => (
        <li key={`${detection.label}-${index}`}>
          {detection.label}
          {detection.distance_m != null && ` — ${detection.distance_m} m`}
        </li>
      ))}
    </ul>
  );
}

export default DetectionList;
