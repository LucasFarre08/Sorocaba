SELECT * FROM telemetria_db.ociosidade;
SET SQL_SAFE_UPDATES = 0;
START TRANSACTION;

DELETE FROM telemetria_db.ociosidade
WHERE combustivel_gasto NOT BETWEEN 0 AND 1000;

SELECT * FROM telemetria_db.ociosidade;

COMMIT;
