CREATE OR REPLACE VIEW gold_kpis AS
SELECT
  (SELECT max(year) FROM data_quality) AS year,
  (SELECT count(*) FROM silver_procurements) AS procurement_count,
  (SELECT count(*) FROM silver_procurements WHERE status='EM ANDAMENTO') AS open_procurements,
  (SELECT coalesce(sum(estimated_value), 0) FROM silver_procurements) AS estimated_value,
  (SELECT coalesce(sum(awarded_value), 0) FROM silver_procurements) AS awarded_value,
  (
    SELECT coalesce(sum(estimated_value - awarded_value), 0)
    FROM silver_procurements
    WHERE estimated_value IS NOT NULL AND awarded_value IS NOT NULL
  ) AS procurement_savings,
  (SELECT count(*) FROM silver_contracts) AS contract_count,
  (SELECT count(*) FROM silver_contracts WHERE status='Contrato Vigente') AS active_contracts,
  (SELECT coalesce(sum(current_value), 0) FROM silver_contracts) AS contract_value,
  (SELECT count(*) FROM silver_expenses) AS creditor_count,
  (SELECT count(*) FROM silver_expenses WHERE document_type='cnpj') AS company_creditor_count,
  (SELECT count(*) FROM silver_expenses WHERE document_type='cpf') AS person_creditor_count,
  (SELECT coalesce(sum(committed_value), 0) FROM silver_expenses) AS committed_value,
  (SELECT coalesce(sum(settled_value), 0) FROM silver_expenses) AS settled_value,
  (SELECT coalesce(sum(paid_value), 0) FROM silver_expenses) AS paid_value,
  (
    SELECT coalesce(sum(committed_value), 0)
    FROM silver_expenses WHERE document_type='cpf'
  ) AS person_committed_value,
  (
    SELECT coalesce(sum(settled_value), 0)
    FROM silver_expenses WHERE document_type='cpf'
  ) AS person_settled_value,
  (
    SELECT coalesce(sum(paid_value), 0)
    FROM silver_expenses WHERE document_type='cpf'
  ) AS person_paid_value,
  (
    SELECT coalesce(sum(committed_value - paid_value), 0)
    FROM silver_expenses
  ) AS committed_balance;

CREATE OR REPLACE VIEW gold_opportunities AS
SELECT
  procurement_id,
  number,
  year,
  object_text,
  search_text,
  agency,
  modality,
  status,
  published_on,
  session_on,
  estimated_value,
  has_document,
  CASE status
    WHEN 'EM ANDAMENTO' THEN 100
    WHEN 'PARALISADO' THEN 45
    WHEN 'PRORROGAÇÃO' THEN 35
    ELSE 0
  END
  + CASE WHEN estimated_value IS NOT NULL THEN 10 ELSE 0 END
  + CASE WHEN has_document THEN 5 ELSE 0 END AS relevance_score
FROM silver_procurements
WHERE status IN ('EM ANDAMENTO', 'PARALISADO', 'PRORROGAÇÃO');

CREATE OR REPLACE VIEW gold_contract_renewals AS
SELECT
  contract_id,
  number,
  object_text,
  agency,
  supplier_name,
  cnpj,
  ends_on,
  date_diff('day', current_date, ends_on) AS days_to_end,
  current_value,
  status,
  has_document
FROM silver_contracts
WHERE ends_on IS NOT NULL AND ends_on >= current_date;

CREATE OR REPLACE VIEW gold_agencies AS
WITH contracts AS (
  SELECT
    agency,
    count(*) AS contract_count,
    coalesce(sum(current_value), 0) AS contract_value
  FROM silver_contracts
  WHERE agency IS NOT NULL
  GROUP BY agency
), procurements AS (
  SELECT
    agency,
    count(*) AS procurement_count,
    count(*) FILTER (WHERE status='EM ANDAMENTO') AS open_procurements,
    coalesce(sum(estimated_value), 0) AS estimated_value,
    coalesce(sum(awarded_value), 0) AS awarded_value
  FROM silver_procurements
  WHERE agency IS NOT NULL
  GROUP BY agency
)
SELECT
  coalesce(c.agency, p.agency) AS agency,
  coalesce(c.contract_count, 0) AS contract_count,
  coalesce(c.contract_value, 0) AS contract_value,
  coalesce(p.procurement_count, 0) AS procurement_count,
  coalesce(p.open_procurements, 0) AS open_procurements,
  coalesce(p.estimated_value, 0) AS estimated_value,
  coalesce(p.awarded_value, 0) AS awarded_value
FROM contracts c FULL OUTER JOIN procurements p ON p.agency=c.agency;

CREATE OR REPLACE VIEW gold_suppliers AS
WITH contracts AS (
  SELECT
    cnpj,
    max(coalesce(supplier_name, supplier_trade_name)) AS supplier_name,
    count(*) AS contract_count,
    coalesce(sum(current_value), 0) AS contract_value
  FROM silver_contracts
  WHERE cnpj IS NOT NULL
  GROUP BY cnpj
), expenses AS (
  SELECT
    cnpj,
    max(coalesce(creditor_legal_name, creditor_name)) AS supplier_name,
    count(*) AS expense_records,
    coalesce(sum(committed_value), 0) AS committed_value,
    coalesce(sum(paid_value), 0) AS paid_value
  FROM silver_expenses
  WHERE cnpj IS NOT NULL
  GROUP BY cnpj
)
SELECT
  coalesce(c.cnpj, e.cnpj) AS cnpj,
  coalesce(c.supplier_name, e.supplier_name) AS supplier_name,
  strip_accents(lower(coalesce(c.supplier_name, e.supplier_name, ''))) AS supplier_search,
  coalesce(c.contract_count, 0) AS contract_count,
  coalesce(c.contract_value, 0) AS contract_value,
  coalesce(e.expense_records, 0) AS expense_records,
  coalesce(e.committed_value, 0) AS committed_value,
  coalesce(e.paid_value, 0) AS paid_value
FROM contracts c FULL OUTER JOIN expenses e ON e.cnpj=c.cnpj;

CREATE OR REPLACE VIEW gold_person_creditors AS
SELECT
  creditor_id,
  year,
  coalesce(creditor_legal_name, creditor_name, 'Nome não informado') AS person_name,
  search_text AS person_search,
  cpf_masked,
  coalesce(committed_value, 0) AS committed_value,
  coalesce(settled_value, 0) AS settled_value,
  coalesce(paid_value, 0) AS paid_value,
  round(100 * paid_value / nullif(committed_value, 0), 1) AS payment_rate
FROM silver_expenses
WHERE document_type='cpf';

CREATE OR REPLACE VIEW gold_procurement_pipeline AS
SELECT
  coalesce(status, 'NÃO INFORMADO') AS status,
  count(*) AS procurement_count,
  coalesce(sum(estimated_value), 0) AS estimated_value,
  coalesce(sum(awarded_value), 0) AS awarded_value
FROM silver_procurements
GROUP BY status;

CREATE OR REPLACE VIEW gold_contract_links AS
SELECT
  c.*,
  p.status AS procurement_status,
  p.session_on AS procurement_session_on,
  p.estimated_value AS procurement_estimated_value,
  p.awarded_value AS procurement_awarded_value,
  p.procurement_id IS NOT NULL AS procurement_linked
FROM silver_contracts c
LEFT JOIN silver_procurements p ON p.procurement_id=c.procurement_id;

CREATE OR REPLACE VIEW gold_quality AS
SELECT
  resource,
  year,
  source_records,
  accepted_records,
  rejected_records,
  cnpj_records,
  cpf_masked_records,
  invalid_document_records,
  round(100.0 * accepted_records / nullif(source_records, 0), 2) AS acceptance_rate
FROM data_quality;
