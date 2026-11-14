-- Tiger Data schema for storage/ (SPEC.md section 4.10). Safe to run on every start.

CREATE EXTENSION IF NOT EXISTS timescaledb;

CREATE TABLE IF NOT EXISTS touch_events (
    ts          timestamptz NOT NULL,
    session_id  text        NOT NULL,
    object_id   integer     NOT NULL,
    class_label text        NOT NULL,
    name        text        NOT NULL DEFAULT '',
    kind        text        NOT NULL,
    cx          real        NOT NULL,
    cy          real        NOT NULL,
    neighbours  text[]      NOT NULL DEFAULT '{}'
);

SELECT create_hypertable('touch_events', 'ts', if_not_exists => TRUE);

CREATE INDEX IF NOT EXISTS touch_events_ts_desc_idx ON touch_events (ts DESC);

CREATE TABLE IF NOT EXISTS hazard_events (
    ts          timestamptz NOT NULL,
    session_id  text        NOT NULL,
    type        text        NOT NULL,
    source      text        NOT NULL,
    confidence  real        NOT NULL
);

SELECT create_hypertable('hazard_events', 'ts', if_not_exists => TRUE);
