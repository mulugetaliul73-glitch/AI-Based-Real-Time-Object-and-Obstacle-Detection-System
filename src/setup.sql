CREATE TABLE detections (
    id SERIAL PRIMARY KEY,
    label VARCHAR(64) NOT NULL,
    confidence DOUBLE PRECISION NOT NULL,
    distance_m DOUBLE PRECISION,
    direction VARCHAR(16) NOT NULL,
    danger_level VARCHAR(16) NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX ix_detections_label ON detections (label);
CREATE INDEX ix_detections_danger_level ON detections (danger_level);
CREATE INDEX ix_detections_created_at ON detections (created_at);