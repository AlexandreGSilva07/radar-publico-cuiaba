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
  simples BOOLEAN,
  mei BOOLEAN,
  source_url VARCHAR NOT NULL,
  fetched_at TIMESTAMP NOT NULL
);

CREATE TABLE IF NOT EXISTS enrichment_attempt(
  cnpj VARCHAR NOT NULL,
  attempted_at TIMESTAMP NOT NULL,
  status VARCHAR NOT NULL,
  http_status INTEGER,
  reason VARCHAR
);

