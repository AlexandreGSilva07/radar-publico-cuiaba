CREATE TABLE IF NOT EXISTS analytics_metadata(
  key VARCHAR PRIMARY KEY,
  value VARCHAR NOT NULL
);

CREATE TABLE IF NOT EXISTS silver_contracts(
  contract_id BIGINT PRIMARY KEY,
  number VARCHAR,
  year INTEGER NOT NULL,
  object_text VARCHAR,
  search_text VARCHAR NOT NULL,
  agency VARCHAR,
  supplier_name VARCHAR,
  supplier_trade_name VARCHAR,
  document_type VARCHAR NOT NULL,
  cnpj VARCHAR,
  status_code VARCHAR,
  status VARCHAR,
  signed_on DATE,
  starts_on DATE,
  ends_on DATE,
  contract_type VARCHAR,
  category VARCHAR,
  procurement_id BIGINT,
  procurement_number VARCHAR,
  procurement_year INTEGER,
  procurement_modality VARCHAR,
  original_value DECIMAL(18, 2),
  current_value DECIMAL(18, 2),
  has_document BOOLEAN NOT NULL,
  source_run_id VARCHAR NOT NULL,
  source_hash VARCHAR NOT NULL
);

CREATE TABLE IF NOT EXISTS silver_procurements(
  procurement_id BIGINT PRIMARY KEY,
  number VARCHAR,
  year INTEGER NOT NULL,
  object_text VARCHAR,
  search_text VARCHAR NOT NULL,
  agency VARCHAR,
  modality VARCHAR,
  status VARCHAR,
  published_on DATE,
  session_on DATE,
  proposal_opens_on DATE,
  estimated_value DECIMAL(18, 2),
  awarded_value DECIMAL(18, 2),
  winner_name VARCHAR,
  winner_legal_name VARCHAR,
  has_document BOOLEAN NOT NULL,
  source_run_id VARCHAR NOT NULL,
  source_hash VARCHAR NOT NULL
);

CREATE TABLE IF NOT EXISTS silver_expenses(
  year INTEGER NOT NULL,
  creditor_id BIGINT NOT NULL,
  creditor_name VARCHAR,
  creditor_legal_name VARCHAR,
  search_text VARCHAR NOT NULL,
  document_type VARCHAR NOT NULL,
  cnpj VARCHAR,
  cpf_masked VARCHAR,
  committed_value DECIMAL(18, 2),
  settled_value DECIMAL(18, 2),
  paid_value DECIMAL(18, 2),
  source_run_id VARCHAR NOT NULL,
  source_hash VARCHAR NOT NULL,
  PRIMARY KEY(year, creditor_id)
);

CREATE TABLE IF NOT EXISTS data_quality(
  resource VARCHAR NOT NULL,
  year INTEGER NOT NULL,
  source_records INTEGER NOT NULL,
  accepted_records INTEGER NOT NULL,
  rejected_records INTEGER NOT NULL,
  cnpj_records INTEGER NOT NULL,
  cpf_masked_records INTEGER NOT NULL,
  invalid_document_records INTEGER NOT NULL,
  PRIMARY KEY(resource, year)
);

CREATE TABLE IF NOT EXISTS transform_rejections(
  resource VARCHAR NOT NULL,
  year INTEGER NOT NULL,
  record_index INTEGER NOT NULL,
  reason VARCHAR NOT NULL,
  source_hash VARCHAR NOT NULL
);
