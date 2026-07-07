SELECT * FROM telemetria_db.viagens;
SET SQL_SAFE_UPDATES = 0;
DELETE FROM telemetria_db.viagens
WHERE (quilometragem < 0 OR quilometragem > 30000)
   OR (litros_consumidos < 0 OR litros_consumidos > 10000);
SELECT * FROM telemetria_db.viagens;