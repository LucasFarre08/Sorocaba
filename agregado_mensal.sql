SET SQL_SAFE_UPDATES = 0;

CREATE TABLE IF NOT EXISTS telemetria_maersk.agregado_mensal (
  grouping_id VARCHAR(64) NOT NULL,
  ano_mes DATE NOT NULL,
  km_total DECIMAL(14,2) DEFAULT 0,
  litros_total DECIMAL(14,2) DEFAULT 0,
  PRIMARY KEY (grouping_id, ano_mes)
) ENGINE=InnoDB;

START TRANSACTION;

-- 1) tabela temporária normalizada
DROP TEMPORARY TABLE IF EXISTS tmp_agregado;
CREATE TEMPORARY TABLE tmp_agregado (
  grouping_id VARCHAR(64) NOT NULL,
  ano_mes DATE NOT NULL,
  km_total DECIMAL(14,2),
  litros_total DECIMAL(14,2)
) ENGINE=InnoDB;

INSERT INTO tmp_agregado (grouping_id, ano_mes, km_total, litros_total)
SELECT
  REPLACE(REPLACE(TRIM(UPPER(`grouping`)), '.', ''), '-', '') AS grouping_id,
  DATE_FORMAT(`inicio`, '%Y-%m-01') AS ano_mes,
  ROUND(SUM(IFNULL(quilometragem,0)), 2) AS km_total,
  ROUND(SUM(IFNULL(litros_consumidos,0)), 2) AS litros_total
FROM telemetria_maersk.viagens
WHERE `inicio` IS NOT NULL
  AND TRIM(`grouping`) <> ''
GROUP BY
  grouping_id,
  ano_mes;

-- 2) atualizar registros existentes
UPDATE telemetria_maersk.agregado_mensal a
JOIN tmp_agregado t
  ON a.grouping_id = t.grouping_id
 AND a.ano_mes = t.ano_mes
SET
  a.km_total = t.km_total,
  a.litros_total = t.litros_total;

-- 3) inserir apenas os novos
INSERT INTO telemetria_maersk.agregado_mensal (grouping_id, ano_mes, km_total, litros_total)
SELECT
  t.grouping_id,
  t.ano_mes,
  t.km_total,
  t.litros_total
FROM tmp_agregado t
LEFT JOIN telemetria_maersk.agregado_mensal a
  ON a.grouping_id = t.grouping_id
 AND a.ano_mes = t.ano_mes
WHERE a.grouping_id IS NULL;

DROP TEMPORARY TABLE IF EXISTS tmp_agregado;

COMMIT;
