# Wialon Report Runner + SQL Logger

Executa relatórios do Wialon e registra logs no SQLite.

## Instalação
```bash
pip install -r requirements.txt
```

## Uso
```bash
python wialon_report_sql.py --token SEU_TOKEN   --resource-id 400915337 --template-id 28 --object-id 400914415   --from "2025-08-01 00:00:00" --to "2025-08-05 23:59:59"   --format xlsx --output Relatorio_Wialon --db wialon_logs.db
```
