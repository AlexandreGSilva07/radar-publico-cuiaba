CREATE TABLE IF NOT EXISTS company_profile(
  cnpj VARCHAR PRIMARY KEY,
  cnpj_root VARCHAR NOT NULL,
  legal_name VARCHAR,
  trade_name VARCHAR,
  registration_status VARCHAR,
  status_on DATE,
  opened_on DATE,
  headquarters_type VARCHAR,
  company_size VARCHAR,
  legal_nature VARCHAR,
  share_capital DECIMAL(18, 2),
  primary_cnae VARCHAR,
  primary_cnae_description VARCHAR,
  secondary_cnaes_json VARCHAR NOT NULL,
  state VARCHAR,
  city VARCHAR,
  district VARCHAR,
  street VARCHAR,
  street_number VARCHAR,
  address_extra VARCHAR,
  postal_code VARCHAR,
  phone_primary VARCHAR,
  phone_secondary VARCHAR,
  email VARCHAR,
  tax_regime VARCHAR,
  tax_regime_year INTEGER,
  municipality_ibge INTEGER,
  simples BOOLEAN,
  mei BOOLEAN,
  source_url VARCHAR NOT NULL,
  fetched_at TIMESTAMP NOT NULL
);

ALTER TABLE company_profile ADD COLUMN IF NOT EXISTS phone_primary VARCHAR;
ALTER TABLE company_profile ADD COLUMN IF NOT EXISTS phone_secondary VARCHAR;
ALTER TABLE company_profile ADD COLUMN IF NOT EXISTS email VARCHAR;
ALTER TABLE company_profile ADD COLUMN IF NOT EXISTS tax_regime VARCHAR;
ALTER TABLE company_profile ADD COLUMN IF NOT EXISTS tax_regime_year INTEGER;
ALTER TABLE company_profile ADD COLUMN IF NOT EXISTS municipality_ibge INTEGER;

CREATE TABLE IF NOT EXISTS enrichment_attempt(
  cnpj VARCHAR NOT NULL,
  attempted_at TIMESTAMP NOT NULL,
  status VARCHAR NOT NULL,
  http_status INTEGER,
  reason VARCHAR
);

CREATE TABLE IF NOT EXISTS company_location(
  postal_code VARCHAR PRIMARY KEY,
  state VARCHAR,
  city VARCHAR,
  district VARCHAR,
  street VARCHAR,
  provider VARCHAR,
  longitude DOUBLE,
  latitude DOUBLE,
  source_url VARCHAR NOT NULL,
  fetched_at TIMESTAMP NOT NULL
);

CREATE TABLE IF NOT EXISTS geocoding_attempt(
  postal_code VARCHAR NOT NULL,
  attempted_at TIMESTAMP NOT NULL,
  status VARCHAR NOT NULL,
  http_status INTEGER,
  reason VARCHAR
);
