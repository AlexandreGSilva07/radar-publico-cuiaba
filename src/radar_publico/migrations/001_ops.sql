CREATE TABLE IF NOT EXISTS schema_migration(version INTEGER PRIMARY KEY, applied_at TIMESTAMP);
CREATE TABLE IF NOT EXISTS run(
  run_id VARCHAR PRIMARY KEY,
  run_key VARCHAR UNIQUE NOT NULL,
  cycle_id VARCHAR NOT NULL,
  resource VARCHAR NOT NULL,
  year INTEGER NOT NULL,
  status VARCHAR NOT NULL,
  started_at TIMESTAMP NOT NULL,
  finished_at TIMESTAMP
);
CREATE TABLE IF NOT EXISTS request(
  request_id VARCHAR PRIMARY KEY,
  run_id VARCHAR NOT NULL,
  page INTEGER NOT NULL,
  status VARCHAR NOT NULL,
  record_count INTEGER,
  total_records INTEGER,
  finished_at TIMESTAMP,
  UNIQUE(run_id, page)
);
CREATE TABLE IF NOT EXISTS bronze_object(
  object_id VARCHAR PRIMARY KEY,
  content_hash VARCHAR UNIQUE NOT NULL,
  storage_path VARCHAR NOT NULL,
  created_at TIMESTAMP NOT NULL
);
CREATE TABLE IF NOT EXISTS bronze_reference(
  reference_id VARCHAR PRIMARY KEY,
  request_id VARCHAR NOT NULL,
  object_id VARCHAR NOT NULL,
  is_current BOOLEAN NOT NULL,
  created_at TIMESTAMP NOT NULL
);
CREATE TABLE IF NOT EXISTS coverage(
  run_id VARCHAR PRIMARY KEY,
  expected_pages INTEGER,
  collected_pages INTEGER NOT NULL,
  expected_records INTEGER,
  collected_records INTEGER NOT NULL,
  status VARCHAR NOT NULL,
  updated_at TIMESTAMP NOT NULL
);
