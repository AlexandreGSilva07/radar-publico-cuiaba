CREATE TABLE IF NOT EXISTS agency_directory(
  source_url VARCHAR PRIMARY KEY,
  directory_kind VARCHAR NOT NULL,
  slug VARCHAR NOT NULL,
  agency_name VARCHAR NOT NULL,
  address VARCHAR,
  postal_code VARCHAR,
  phones_json VARCHAR NOT NULL,
  emails_json VARCHAR NOT NULL,
  source_hash VARCHAR NOT NULL,
  fetched_at TIMESTAMP NOT NULL
);

CREATE TABLE IF NOT EXISTS agency_directory_attempt(
  source_url VARCHAR NOT NULL,
  attempted_at TIMESTAMP NOT NULL,
  status VARCHAR NOT NULL,
  http_status INTEGER,
  reason VARCHAR
);
