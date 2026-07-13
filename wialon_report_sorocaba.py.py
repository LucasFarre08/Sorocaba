#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Wialon Report Runner + MySQL Logger — VERBOSE + TIMEOUT + RETRY
"""

import argparse
import json
import os
import sys
import time
import re
import io
import random
from datetime import datetime, timezone

import requests
from dotenv import load_dotenv
import mysql.connector

# ======== Wialon constants ========
DEFAULT_BASE_URL = "https://hst-api.wialon.com/wialon/ajax.html"
FORMAT_MAP = {"html": 1, "pdf": 2, "xls": 4, "xlsx": 8, "xml": 16, "csv": 32}
EXT_BY_FORMAT = {1: "html", 2: "pdf", 4: "xls", 8: "xlsx", 16: "xml", 32: "csv"}


def to_epoch_seconds(value: str) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        pass
    v = value.strip().replace("T", " ").replace("Z", "")
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d"):
        try:
            dt = datetime.strptime(v, fmt).replace(tzinfo=timezone.utc)
            return int(dt.timestamp())
        except ValueError:
            continue
    dt = datetime.fromisoformat(v)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return int(dt.timestamp())


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def daterange_days(end_ts: int, days_back: int):
    """Gera janelas diárias UTC [00:00:00..23:59:59] para trás a partir de end_ts."""
    DAY = 86400
    end_day = end_ts // DAY
    for d in range(days_back):
        day = end_day - d
        from_ts = day * DAY
        to_ts = day * DAY + (DAY - 1)
        yield from_ts, to_ts


# ======== util ========
def dest_table_for_template(tid: int, resource_id: int | None = None) -> str:
    """
    Mapeia template_id para a tabela de destino.
    Permite exceções por cliente (resource_id).
    """

    # ===== EXCEÇÃO MAERSK =====
    if resource_id == 401149512 and tid == 34:
        return "viagens"

    # ===== PADRÃO =====
    mapping = {
        43: "viagens",
        34: "ociosidade",
        113: "rpm_amarelo",
        39: "rpm_vermelho",
        56: "kickdown",
        41: "velocidade_chuva_60km",
        40: "velocidade_80km",
        31: "seguranca",
        36: "freio",
        21: "motoristas_viagens",
    }

    return mapping.get(tid, "report_data")

# ======== MySQL logger ========
class SqlLogger:
    def __init__(self, host="localhost", user="root", password="", database="Pontual_db"):
        self.conn = mysql.connector.connect(host=host, user=user, password=password, database=database)
        self.cur = self.conn.cursor()
        self._ensure_schema()

    def _ensure_schema(self):
        self.cur.execute("SET FOREIGN_KEY_CHECKS=1;")
        # runs
        self.cur.execute("""
        CREATE TABLE IF NOT EXISTS runs (
            id INT AUTO_INCREMENT PRIMARY KEY,
            started_at DATETIME,
            base_url TEXT,
            sid VARCHAR(255),
            token_used TINYINT,
            resource_id BIGINT,
            template_id BIGINT,
            object_id BIGINT,
            from_ts BIGINT,
            to_ts BIGINT,
            remote_exec TINYINT,
            fmt VARCHAR(20),
            output_path TEXT,
            finished_at DATETIME,
            final_status VARCHAR(20),
            error TEXT
        ) ENGINE=InnoDB;
        """)
        # steps
        self.cur.execute("""
        CREATE TABLE IF NOT EXISTS steps (
            id INT AUTO_INCREMENT PRIMARY KEY,
            run_id INT,
            at DATETIME,
            step VARCHAR(100),
            svc VARCHAR(100),
            params_json JSON,
            ok TINYINT,
            http_status INT,
            response_json JSON,
            error TEXT,
            FOREIGN KEY(run_id) REFERENCES runs(id) ON DELETE CASCADE
        ) ENGINE=InnoDB;
        """)
        # files (BLOB)
        self.cur.execute("""
        CREATE TABLE IF NOT EXISTS files (
            id INT AUTO_INCREMENT PRIMARY KEY,
            run_id INT NOT NULL,
            created_at DATETIME NOT NULL,
            filename VARCHAR(255) NOT NULL,
            mime VARCHAR(100),
            size_bytes BIGINT,
            content LONGBLOB,
            FOREIGN KEY(run_id) REFERENCES runs(id) ON DELETE CASCADE
        ) ENGINE=InnoDB;
        """)
        # data tabular (fallback genérico)
        self.cur.execute("""
        CREATE TABLE IF NOT EXISTS report_data (
            id BIGINT AUTO_INCREMENT PRIMARY KEY,
            run_id INT NOT NULL,
            sheet_name VARCHAR(255) NULL
        ) ENGINE=InnoDB;
        """)

        # tabelas específicas Pontual (recebem colunas dinâmicas no import)

        #tabelas geral
        self.cur.execute("""
        CREATE TABLE IF NOT EXISTS kickdown (
            id BIGINT AUTO_INCREMENT PRIMARY KEY,
            run_id INT NOT NULL,
            sheet_name VARCHAR(255) NULL,
            ativado datetime,
            duracao time
        ) ENGINE=InnoDB;
        """)
        self.cur.execute("""
        CREATE TABLE IF NOT EXISTS ociosidade (
            id BIGINT AUTO_INCREMENT PRIMARY KEY,
            run_id INT NOT NULL,
            sheet_name VARCHAR(255) NULL,
            ativado datetime,
            duracao time,
            combustivel_gasto float
        ) ENGINE=InnoDB;
        """)
        self.cur.execute("""
        CREATE TABLE IF NOT EXISTS rpm_amarelo (
            id BIGINT AUTO_INCREMENT PRIMARY KEY,
            run_id INT NOT NULL,
            sheet_name VARCHAR(255) NULL,
            ativado datetime,
            duracao time
        ) ENGINE=InnoDB;
        """)
        self.cur.execute("""
        CREATE TABLE IF NOT EXISTS rpm_vermelho (
            id BIGINT AUTO_INCREMENT PRIMARY KEY,
            run_id INT NOT NULL,
            sheet_name VARCHAR(255) NULL,
            ativado datetime,
            duracao time,
            rpm_maximo INT                         
        ) ENGINE=InnoDB;
        """)
        self.cur.execute("""
        CREATE TABLE IF NOT EXISTS velocidade_80km (
            id BIGINT AUTO_INCREMENT PRIMARY KEY,
            run_id INT NOT NULL,
            sheet_name VARCHAR(255) NULL,
            ativado datetime,
            duracao time,
            velocidade_maxima INT
        ) ENGINE=InnoDB;
        """)
        self.cur.execute("""
        CREATE TABLE IF NOT EXISTS velocidade_chuva_60km (
            id BIGINT AUTO_INCREMENT PRIMARY KEY,
            run_id INT NOT NULL,
            sheet_name VARCHAR(255) NULL,
            ativado datetime,
            duracao time,
            velocidade_maxima INT
        ) ENGINE=InnoDB;
        """)
        self.cur.execute("""
        CREATE TABLE IF NOT EXISTS viagens (
            id BIGINT AUTO_INCREMENT PRIMARY KEY,
            run_id INT NOT NULL,
            sheet_name VARCHAR(255) NULL,
            inicio datetime,
            fim datetime,
            quilometragem float,
            litros_consumidos float,
            duracao time,
            quilometragem_inicial float,
            quilometragem_final float,
            horas_de_motor float
        ) ENGINE=InnoDB;
        """)
        self.cur.execute("""
        CREATE TABLE IF NOT EXISTS seguranca (
            id BIGINT AUTO_INCREMENT PRIMARY KEY,
            run_id INT NOT NULL,
            sheet_name VARCHAR(255) NULL,
            velocidade INT,
            data datetime,
            evento INT
        ) ENGINE=InnoDB;
        """)
        self.cur.execute("""
        CREATE TABLE IF NOT EXISTS freio (
            id BIGINT AUTO_INCREMENT PRIMARY KEY,
            run_id INT NOT NULL,
            sheet_name VARCHAR(255) NULL,
            ativado datetime,
            duracao time
        ) ENGINE=InnoDB;
        """)
        self.cur.execute("""
        CREATE TABLE IF NOT EXISTS embreagem (
            id BIGINT AUTO_INCREMENT PRIMARY KEY,
            run_id INT NOT NULL,
            sheet_name VARCHAR(255) NULL,
            ativado datetime,
            duracao time
        ) ENGINE=InnoDB;
        """)
        self.cur.execute("""
        CREATE TABLE IF NOT EXISTS clia (
            id BIGINT AUTO_INCREMENT PRIMARY KEY,
            run_id INT NOT NULL,
            sheet_name VARCHAR(255) NULL                       
        ) ENGINE=InnoDB;
        """)
        self.cur.execute("""
        CREATE TABLE IF NOT EXISTS filial_entrada (
            id BIGINT AUTO_INCREMENT PRIMARY KEY,
            run_id INT NOT NULL,
            sheet_name VARCHAR(255) NULL,
            inicio datetime,
            fim datetime,
            tempo_total time,
            duracao_de_estacionamentos time,
            tempo_entre time,
            quilometragem float,
            litros_consumidos float,
            duracao time,
            quilometragem_inicial float,
            quilometragem_final float                         
        ) ENGINE=InnoDB;
        """)
        self.cur.execute("""
        CREATE TABLE IF NOT EXISTS operadores_portuarios (
            id BIGINT AUTO_INCREMENT PRIMARY KEY,
            run_id INT NOT NULL,
            sheet_name VARCHAR(255) NULL,
            inicio datetime,
            fim datetime,
            tempo_total time,
            duracao_de_estacionamentos time,
            tempo_entre time,
            quilometragem float,
            litros_consumidos float,
            duracao time,
            quilometragem_inicial float,
            quilometragem_final float                         
        ) ENGINE=InnoDB;
        """)

        self.conn.commit()

    # -------- lifecycle ----------
    def start_run(self, base_url, sid, token_used, resource_id, template_id,
                    object_id, from_ts, to_ts, remote_exec, fmt, output_path):
        self.cur.execute("""
            INSERT INTO runs (started_at, base_url, sid, token_used, resource_id, template_id,
                              object_id, from_ts, to_ts, remote_exec, fmt, output_path)
            VALUES (NOW(), %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s);
        """, (base_url, sid, int(token_used), resource_id, template_id, object_id,
              from_ts, to_ts, int(remote_exec), fmt, output_path))
        self.conn.commit()
        return self.cur.lastrowid

    def log_step(self, run_id, step, svc, params, http_status, ok, response=None, error=None):
        self.cur.execute("""
            INSERT INTO steps (run_id, at, step, svc, params_json, ok, http_status, response_json, error)
            VALUES (%s, NOW(), %s, %s, %s, %s, %s, %s, %s);
        """, (run_id, step, svc, json.dumps(params), int(ok), http_status,
              json.dumps(response) if response is not None else None, error))
        self.conn.commit()

    def finish_run(self, run_id, final_status, error):
        self.cur.execute("""UPDATE runs SET finished_at=NOW(), final_status=%s, error=%s WHERE id=%s;""",
                         (final_status, error, run_id))
        self.conn.commit()

    # -------- arquivos ----------
    def insert_file_blob(self, run_id: int, filename: str, mime: str, content: bytes):
        self.cur.execute("""
            INSERT INTO files (run_id, created_at, filename, mime, size_bytes, content)
            VALUES (%s, NOW(), %s, %s, %s, %s);
        """, (run_id, filename, mime, len(content), content))
        self.conn.commit()

    def close(self):
        """Fecha cursor e conexão com segurança."""
        try:
            if hasattr(self, "cur") and self.cur:
                try:
                    self.cur.close()
                except Exception:
                    pass
        except Exception:
            pass
        try:
            if hasattr(self, "conn") and self.conn:
                try:
                    self.conn.commit()
                except Exception:
                    pass
                try:
                    self.conn.close()
                except Exception:
                    pass
        except Exception:
            pass

    # -------- CSV/XLSX -> MySQL (arquivo em memória OU caminho) ----------
    def import_tabular_to_sql(self, run_id: int, file_obj_or_path, table_name: str = "report_data"):
        import pandas as pd
        from unidecode import unidecode
        import os
        from dateutil import parser

        # --- Funções auxiliares aninhadas para manter o escopo limpo ---
        def normalize(col: str) -> str:
            c = unidecode(str(col)).strip().lower()
            c = re.sub(r"[^a-z0-9]+", "_", c)
            c = re.sub(r"_+", "_", c).strip("_")
            return c or "col"

        def find_header_row(df: "pd.DataFrame") -> int:
            keywords = {"n", "no", "grouping", "sensor", "motorista", "duracao",
                        "localizacao", "início", "inicio", "fim", "data", "tempo", "duracao", "ativado"}
            for i in range(min(25, len(df))):
                row = df.iloc[i].astype(str).str.strip()
                row_norm = {normalize(x) for x in row if x and x != "nan"}
                non_empty = (row != "").sum()
                if (keywords & row_norm) or non_empty >= 3:
                    return i
            return 0

        def read_best_xlsx(x):
            xls = pd.ExcelFile(x, engine="openpyxl")
            best_df, best_name, best_score = None, None, -1
            for name in xls.sheet_names:
                raw = pd.read_excel(xls, sheet_name=name, header=None)
                hdr = find_header_row(raw)
                tmp = pd.read_excel(xls, sheet_name=name, header=hdr)
                score = tmp.dropna(axis=1, how="all").shape[1]
                if score > best_score and score >= 2:
                    best_df, best_name, best_score = tmp, name, score
            return best_df, best_name

        def format_datetime_val(val):
            try:
                dt = parser.parse(str(val), fuzzy=True, dayfirst=True)
                return dt.strftime('%Y-%m-%d %H:%M:%S')
            except Exception:
                return val

        def parse_duration(val):
            try:
                parts = re.split(r'[: ]', str(val).strip())
                parts = [int(p) for p in parts if p.isdigit()]
                if len(parts) == 3:
                    h, m, s = parts
                    total_seconds = h * 3600 + m * 60 + s
                elif len(parts) == 2:
                    m, s = parts
                    total_seconds = m * 60 + s
                elif len(parts) == 1:
                    total_seconds = parts[0]
                else:
                    return val
                days, remainder = divmod(total_seconds, 86400)
                hours, remainder = divmod(remainder, 3600)
                minutes, seconds = divmod(remainder, 60)
                if days > 0:
                    return f"{days} dias {hours:02}:{minutes:02}:{seconds:02}"
                else:
                    return f"{hours:02}:{minutes:02}:{seconds:02}"
            except Exception:
                return val

        def to_decimal(val):
            try:
                s_val = str(val).replace('.', '').replace(',', '.')
                return "{:.2f}".format(float(s_val)).replace('.', ',')
            except Exception:
                return val

        # --- ler CSV/XLSX de BytesIO OU caminho ---
        df = None
        sheet_name = None
        if hasattr(file_obj_or_path, "read"):
            ext = os.path.splitext(getattr(file_obj_or_path, "name", "memory.xlsx"))[1].lower()
            if ext == ".csv":
                df = pd.read_csv(file_obj_or_path, sep=",", encoding="utf-8")
            elif ext in (".xlsx", ".xls"):
                df, sheet_name = read_best_xlsx(file_obj_or_path)
            else:
                try:
                    df, sheet_name = read_best_xlsx(file_obj_or_path)
                except Exception:
                    self.log_step(run_id, "import_tabular_to_sql", "local",
                                  {"reason": "unsupported_extension_mem"}, 0, False, None, "unsupported in-memory file")
                    return
        else:
            path = str(file_obj_or_path)
            lower = path.lower()
            if lower.endswith(".csv"):
                df = pd.read_csv(path, sep=",", encoding="utf-8")
            elif lower.endswith((".xlsx", ".xls")):
                df, sheet_name = read_best_xlsx(path)
            else:
                self.log_step(run_id, "import_tabular_to_sql", "local",
                              {"reason": "unsupported_extension_path", "path": path}, 0, False, None, "unsupported path")
                return

        if df is None or df.empty:
            self.log_step(run_id, "import_tabular_to_sql", "local",
                          {"reason": "empty_dataframe", "sheet_name": sheet_name}, 200, True, {"rows": 0}, None)
            return

        # limpar e normalizar
        df = df.dropna(how="all").dropna(axis=1, how="all")
        if df.shape[1] <= 1 and len(df) > 1:
            raw = df.copy()
            hdr = find_header_row(raw)
            df.columns = range(df.shape[1])
            df = raw.iloc[hdr:].reset_index(drop=True)

        # Aplicar transformações de tipo
        for col in df.columns:
            col_lower = str(col).lower()
            if any(k in col_lower for k in ["data", "inicio", "fim", "ativado"]):
                df[col] = df[col].apply(format_datetime_val)
            elif "duracao" in col_lower or "duração" in col_lower:
                df[col] = df[col].apply(parse_duration)
            elif "numero" in col_lower or "número" in col_lower:
                df[col] = df[col].apply(to_decimal)

        # Normaliza nomes de colunas para serem compatíveis com SQL
        new_cols, seen = [], set()
        for c in df.columns:
            base = normalize(c)
            k = base or "col"
            i = 2
            while k in seen:
                k = f"{base}_{i}"
                i += 1
            seen.add(k)
            new_cols.append(k)
        df.columns = new_cols

        # Garantir colunas na tabela de destino (table_name)
        self.cur.execute(f"SHOW COLUMNS FROM `{table_name}`;")
        existing = {row[0] for row in self.cur.fetchall()}
        required = {"id", "run_id", "sheet_name"}
        for c in df.columns:
            if c not in existing and c not in required:
                self.cur.execute(f"ALTER TABLE `{table_name}` ADD COLUMN `{c}` TEXT NULL;")
        self.conn.commit()

        # Preparar dados para insercao
        df.insert(0, "run_id", run_id)
        if "sheet_name" not in df.columns:
            df.insert(1, "sheet_name", sheet_name)

        cols = df.columns.tolist()
        col_list = ", ".join(f"`{c}`" for c in cols)
        placeholders = ", ".join(["%s"] * len(cols))

        # ---- identificar colunas numéricas por dtype ou nome ----
        import pandas as _pd
        numeric_name_keywords = ("combustivel_gasto", "litros", "velocidade_maxima", "km", "consum", "horas_de_motor", "rpm_maximo", "quilometragem", "litros_consumidos","quilometragem_inicial","quilometragem_final","horas_motor")
        # cols é a lista já criada acima (df.columns.tolist())
        # montar set de colunas que vamos tratar como números
        numeric_cols = set()
        for c in cols:
            # já é coluna 'run_id' ou 'sheet_name' -> não forçar a número
            if c in ("run_id", "sheet_name"):
                continue
            # heurística 1: dtype numérico
            try:
                if _pd.api.types.is_numeric_dtype(df[c]):
                    numeric_cols.add(c)
                    continue
            except Exception:
                pass
            # heurística 2: nome contém keyword
            low = str(c).lower()
            if any(k in low for k in numeric_name_keywords):
                numeric_cols.add(c)

        def clean_cell(v, as_number=False):
            """Limpeza segura. se as_number=True retorna float ou None; senão string limpa ou None."""
            import pandas as pd
            if pd.isna(v):
                return None
            s = str(v).strip()

            # strings vazias ou só traços => None
            if s == "" or re.fullmatch(r"[-–—]{1,}", s):
                return None

            # remover muitas espaços internos (mas manter texto normal)
            s = re.sub(r"\s+", " ", s).strip()

            # se for para número: aplicar limpeza numérica
            if as_number:
                # lidar com (123) -> -123
                if s.startswith("(") and s.endswith(")"):
                    s = "-" + s[1:-1]
                # remover tudo que não é dígito, sinal, ponto ou vírgula
                s_num = re.sub(r"[^0-9\-\.,]", "", s)
                # se contém ponto e vírgula -> ponto = milhares, vírgula = decimal
                if "." in s_num and "," in s_num:
                    s_num = s_num.replace(".", "").replace(",", ".")
                elif "," in s_num and "." not in s_num:
                    s_num = s_num.replace(",", ".")
                # remover pontos extras (milhares) mantendo o último como separador decimal se houver
                if s_num.count(".") > 1:
                    s_num = re.sub(r'\.(?=.*\.)', '', s_num)
                if s_num in ("", "-"):
                    return None
                # tentar converter para float
                if re.fullmatch(r"-?\d+(\.\d+)?", s_num):
                    try:
                        return float(s_num)
                    except Exception:
                        return None
                # tentar extrair primeiro número encontrado
                m = re.search(r"-?\d+(\.\d+)?", s_num)
                if m:
                    try:
                        return float(m.group(0))
                    except Exception:
                        return None
                return None
            else:
                # NÃO forçar número → apenas limpar excesso de caracteres indesejados leves
                # remover caracteres de controle estranhos e trims, manter texto legível
                s = re.sub(r"[\x00-\x1f\x7f]+", "", s)  # control chars
                # se for algo que ficou apenas números (ex: "12345") e era texto, manter como string
                return s if s != "" else None

        # montar records respeitando numeric_cols
        records = []
        for _, row in df.iterrows():
            vals = []
            for col_name, v in zip(cols, row):
                as_num = col_name in numeric_cols
                cleaned = clean_cell(v, as_number=as_num)
                # se coluna numérica e cleaned não for None, garantimos string/float adequado para o DB:
                # o connector aceita float/str; manter float facilita colunas DECIMAL/FLOAT
                vals.append(cleaned)
            records.append(tuple(vals))


        # Inserir no banco (executemany)
        if records:
            try:
                self.cur.executemany(
                    f"INSERT INTO `{table_name}` ({col_list}) VALUES ({placeholders});",
                    records
                )
                self.conn.commit()
                self.log_step(run_id, "import_tabular_to_sql", "local",
                              {"inserted": len(records), "sheet": sheet_name, "table": table_name}, 200, True, {"ok": True}, None)
            except Exception as e:
                # registrar erro e re-levantar para o chamador tratar se necessário
                try:
                    self.conn.rollback()
                except Exception:
                    pass
                self.log_step(run_id, "import_tabular_to_sql", "local",
                              {"file": sheet_name or table_name}, 0, False, None, str(e))
                raise
        else:
            self.log_step(run_id, "import_tabular_to_sql", "local",
                          {"reason": "no_records_after_clean", "table": table_name}, 200, True, {"rows": 0}, None)

    # fim import_tabular_to_sql
    # -------- replicação por cliente (nova funcionalidade) ----------
    def _safe_db_name(self, grupos: str, prefix: str = "cliente_") -> str:
        """Sanitiza o nome do DB a partir do nome do grupo/cliente."""
        if not grupos:
            grupos = "unknown"
        # leva para ascii, remove acentos e caracteres inválidos
        try:
            from unidecode import unidecode
            safe = unidecode(str(grupos))
        except Exception:
            safe = str(grupos)
        safe = re.sub(r"[^a-zA-Z0-9_]+", "_", safe).strip("_")
        if safe == "":
            safe = "cliente"
        return f"{prefix}{safe}"

    def _find_frota_qualified_name(self, preferred_name="frotas"):
        """
        Tenta resolver o nome qualificado da tabela de mapeamento placa->grupos.
        Retorna tupla (schema, table) ou (None, None) se não encontrar.
        Procura primeiro no DB atual (self.conn.database), depois faz lookup em information_schema.
        """
        try:
            current_db = (self.conn.database or "").strip()
            if current_db:
                # verifica se current_db.frotas existe
                self.cur.execute(
                    "SELECT COUNT(*) FROM information_schema.tables WHERE table_schema=%s AND table_name=%s;",
                    (current_db, preferred_name)
                )
                if self.cur.fetchone()[0] > 0:
                    return current_db, preferred_name
            # procurar em toda a instancia por uma tabela chamada preferred_name acessível
            self.cur.execute(
                "SELECT table_schema FROM information_schema.tables WHERE table_name=%s LIMIT 1;",
                (preferred_name,)
            )
            row = self.cur.fetchone()
            if row:
                return row[0], preferred_name
        except Exception:
            pass
        return None, None

    def replicate_run_rows_to_client_dbs(self, run_id: int, src_table: str, plate_col: str = "placa", client_db_prefix: str = "cliente_"):
        """
        Replica as linhas do `src_table` inseridas para `run_id` em DBs por cliente.
        Busca o mapeamento placa->grupos na tabela 'frotas' (qualquer schema acessível).
        """
        try:
            current_db = self.conn.database or ""
            # verificar existência da tabela src_table no DB atual
            self.cur.execute("SELECT COUNT(*) FROM information_schema.tables WHERE table_schema=%s AND table_name=%s;", (current_db, src_table))
            if self.cur.fetchone()[0] == 0:
                self.log_step(run_id, "replicate", "local", {"table": src_table}, 0, False, None, f"src table {src_table} not found in schema {current_db}")
                return 0

            # resolver tabela de frotas (mapping)
            schema_frota, table_frota = self._find_frota_qualified_name("frotas")
            if not schema_frota:
                # fallback: tentar usar apenas 'frotas' sem schema (pode falhar se não no current_db)
                self.log_step(run_id, "replicate", "local", {}, 0, False, None, "mapping table 'frotas' not found in any schema")
                return 0
            mapping_qualified = f"`{schema_frota}`.`{table_frota}`"

            # pegar colunas da tabela src_table
            self.cur.execute(f"SHOW COLUMNS FROM `{src_table}`;")
            cols = [row[0] for row in self.cur.fetchall()]
            if not cols:
                self.log_step(run_id, "replicate", "local", {"table": src_table}, 0, False, None, "no columns found")
                return 0
            cols_no_id = [c for c in cols if c.lower() != "id"]
            if not cols_no_id:
                self.log_step(run_id, "replicate", "local", {"table": src_table}, 0, False, None, "no insertable columns (all id?)")
                return 0
            col_list = ", ".join(f"`{c}`" for c in cols_no_id)
            select_cols = ", ".join(f"`{c}`" for c in cols_no_id)

            # identificar placas distintas no run
            q = f"SELECT DISTINCT `{plate_col}` FROM `{current_db}`.`{src_table}` WHERE run_id = %s AND `{plate_col}` IS NOT NULL;"
            self.cur.execute(q, (run_id,))
            plates = [r[0] for r in self.cur.fetchall() if r[0] is not None]
            if not plates:
                self.log_step(run_id, "replicate", "local", {"table": src_table}, 200, True, {"replicated": 0}, None)
                return 0

            replicated_total = 0
            for placa in plates:
                # lookup grupo usando tabela de mapeamento encontrada
                try:
                    self.cur.execute(f"SELECT grupos FROM {mapping_qualified} WHERE placa = %s LIMIT 1;", (placa,))
                    row = self.cur.fetchone()
                    grupos = row[0] if row else None
                except Exception as e:
                    grupos = None
                    self.log_step(run_id, "replicate", "local", {"plate": placa}, 0, False, None, f"mapping lookup error: {e}")

                target_db = self._safe_db_name(grupos, prefix=client_db_prefix)

                # criar DB se necessário
                try:
                    self.cur.execute(f"CREATE DATABASE IF NOT EXISTS `{target_db}`;")
                except Exception as e:
                    self.log_step(run_id, "replicate", "local", {"plate": placa, "target_db": target_db}, 0, False, None, f"create db error: {e}")
                    continue

                # criar tabela destino LIKE src_table
                try:
                    create_like_sql = f"CREATE TABLE IF NOT EXISTS `{target_db}`.`{src_table}` LIKE `{current_db}`.`{src_table}`;"
                    self.cur.execute(create_like_sql)
                except Exception as e:
                    self.log_step(run_id, "replicate", "local", {"plate": placa, "create_table_like": True}, 0, False, None, str(e))
                    continue

                # copiar linhas
                copy_sql = (
                    f"INSERT INTO `{target_db}`.`{src_table}` ({col_list}) "
                    f"SELECT {select_cols} FROM `{current_db}`.`{src_table}` "
                    f"WHERE run_id = %s AND `{plate_col}` = %s;"
                )
                try:
                    self.cur.execute(copy_sql, (run_id, placa))
                    affected = self.cur.rowcount
                    self.conn.commit()
                    replicated_total += affected if affected is not None else 0
                    self.log_step(run_id, "replicate", "local", {"plate": placa, "target_db": target_db, "rows": affected}, 200, True, {"ok": True}, None)
                except Exception as e:
                    try:
                        self.conn.rollback()
                    except Exception:
                        pass
                    self.log_step(run_id, "replicate", "local", {"plate": placa, "target_db": target_db}, 0, False, None, str(e))
                    continue

            self.log_step(run_id, "replicate_summary", "local", {"table": src_table, "total_replicated": replicated_total}, 200, True, {"replicated": replicated_total}, None)
            return replicated_total

        except Exception as e:
            try:
                self.conn.rollback()
            except Exception:
                pass
            self.log_step(run_id, "replicate", "local", {"table": src_table}, 0, False, None, str(e))
            raise



# ======== Wialon client ========
class WialonClient:
    def __init__(self, base_url, logger, run_id, verbose=False, http_timeout=300):
        self.base_url = base_url
        self.sid = None
        self.logger = logger
        self.run_id = run_id
        self.verbose = verbose
        self.http_timeout = http_timeout

    def _vprint(self, *a, **k):
        if self.verbose:
            print(*a, **k, flush=True)

    def _call(self, step, svc, params, response_binary=False):
        self._vprint(f"[{step}] -> {svc} params={params}")
        last_exc = None
        for attempt in range(3):
            try:
                r = requests.get(
                    self.base_url,
                    params={"svc": svc, "sid": self.sid, "params": json.dumps(params)},
                    timeout=self.http_timeout
                )
                if response_binary:
                    self.logger.log_step(self.run_id, step, svc, params, r.status_code, True)
                    self._vprint(f"[{step}] <- {svc} http={r.status_code} (binário {len(r.content)} bytes)")
                    return r, r.content
                else:
                    try:
                        data = r.json()
                    except Exception:
                        data = {"_non_json": True, "http_status": r.status_code}
                    ok = not (isinstance(data, dict) and "error" in data and data["error"] not in (None, 0))
                    self.logger.log_step(self.run_id, step, svc, params, r.status_code, ok, data, None if ok else "error")
                    self._vprint(f"[{step}] <- {svc} http={r.status_code} ok={ok} resp={data}")
                    if not ok:
                        raise RuntimeError(f"Wialon error on {svc}: {data}")
                    return r, data
            except requests.exceptions.ReadTimeout as e:
                last_exc = e
                self._vprint(f"[{step}] timeout HTTP ({self.http_timeout}s) tentativa {attempt+1}/3; tentando novamente...")
                time.sleep(2 + attempt)
            except requests.exceptions.RequestException as e:
                last_exc = e
                self._vprint(f"[{step}] erro de rede: {e}; tentativa {attempt+1}/3")
                time.sleep(2 + attempt)
        raise last_exc

    def login_by_token(self, token):
        _, data = self._call("login", "token/login", {"token": token})
        self.sid = data.get("eid")
        if not self.sid:
            raise RuntimeError(f"Falha no login: {data}")
        self._vprint(f"[login] SID={self.sid}")
        return self.sid

    def exec_report(self, params): return self._call("exec_report", "report/exec_report", params)[1]
    def get_report_status(self): return self._call("get_report_status", "report/get_report_status", {})[1]
    def apply_report_result(self): return self._call("apply_report_result", "report/apply_report_result", {})[1]
    def export_result(self, params): return self._call("export_result", "report/export_result", params, response_binary=True)[1]

    # ---- busca unidades (id + nome) ----
    def search_units(self, name_mask="*"):
        params = {
            "spec": {
                "itemsType": "avl_unit",
                "propName": "sys_name",
                "propValueMask": name_mask,
                "sortType": "sys_name"
            },
            "force": 1,
            "flags": 1,      # id + nm
            "from": 0,
            "to": 10000
        }
        _, data = self._call("search_units", "core/search_items", params)
        items = data.get("items", []) or []
        return [{"id": it.get("id"), "name": it.get("nm")} for it in items]


# ======== Orquestração ========
def run_flow(base_url, token, sid, mysql_host, mysql_user, mysql_pass, mysql_db,
             resource_id, template_id, object_id, from_value, to_value,
             fmt, output, remote_exec, flags=16777216, verbose=False,
             timeout: int = 300, days: int = None, plates_per_day: int = None,
             unit_filter: str = None, seed: int = None, http_timeout: int = 300,
             split_by_client: bool = False, plate_col: str = "placa", client_db_prefix: str = "cliente_"):
    load_dotenv()
    base_url = base_url or os.getenv("WIALON_BASE_URL", DEFAULT_BASE_URL)
    token = token or os.getenv("WIALON_TOKEN")
    sid = sid or os.getenv("WIALON_SID")

    from_ts = to_epoch_seconds(from_value)
    to_ts = to_epoch_seconds(to_value)

    logger = SqlLogger(
        host=mysql_host,
        user=mysql_user,
        password=mysql_pass,
        database=mysql_db
    )
    run_id = logger.start_run(
        base_url, sid, token is not None, resource_id, template_id,
        object_id, from_ts, to_ts, remote_exec, fmt, output
    )

    client = WialonClient(base_url, logger, run_id, verbose=verbose, http_timeout=http_timeout)

    # Auth
    if sid:
        client.sid = sid
        client._vprint(f"[auth] Usando SID existente: {sid}")
    elif token:
        client.login_by_token(token)
    else:
        logger.finish_run(run_id, None, "Faltou --token ou --sid")
        raise SystemExit("Informe --token ou --sid")

    # ---------- MODO: K placas por dia em X dias ----------
    if days and plates_per_day:
        if seed is not None:
            random.seed(seed)

        units = client.search_units("*")
        if unit_filter:
            rx = re.compile(unit_filter, re.IGNORECASE)
            units = [u for u in units if rx.search(u["name"] or "")]
        if not units:
            logger.finish_run(run_id, None, "Nenhuma unidade encontrada após filtro")
            raise SystemExit("Nenhuma unidade encontrada (ajuste --unit-filter).")

        if verbose:
            print(f"[info] unidades após filtro: {len(units)}")

        fmt_code = FORMAT_MAP.get(fmt.lower(), 8)

        for i, (f_ts, t_ts) in enumerate(daterange_days(to_ts, days), 1):
            pick = random.sample(units, k=min(plates_per_day, len(units)))
            if verbose:
                print(f"[dia {i}] {datetime.utcfromtimestamp(f_ts)} .. {datetime.utcfromtimestamp(t_ts)} | {len(pick)} placas")

            for u in pick:
                exec_params = {
                    "reportResourceId": resource_id,
                    "reportTemplateId": template_id,
                    "reportObjectId": u["id"],
                    "reportObjectSecId": 0,
                    "interval": {"from": f_ts, "to": t_ts, "flags": flags},
                }
                if remote_exec:
                    exec_params["remoteExec"] = 1

                client.exec_report(exec_params)

                if remote_exec:
                    start = time.time()
                    while True:
                        st = client.get_report_status()
                        final_status = str(st.get("status", ""))
                        running = st.get("reportIsRunning")
                        client._vprint(f"[status] status={final_status} running={running}")
                        if final_status == "4":
                            break
                        if final_status == "8":
                            logger.finish_run(run_id, final_status, "Falha no relatório (status=8)")
                            raise RuntimeError("Relatório falhou no Wialon: status=8")
                        if time.time() - start > timeout:
                            logger.finish_run(run_id, final_status, "Timeout esperando relatório")
                            raise TimeoutError("Timeout esperando relatório concluir")
                        time.sleep(1.5)
                    client.apply_report_result()

                exp_params = {"format": fmt_code, "compress": 0, "outputFileName": "Relatorio_Wialon"}
                content = client.export_result(exp_params)

                # --- guardar em MySQL ---
                ext = EXT_BY_FORMAT.get(fmt_code, "bin")
                mime = {
                    "pdf": "application/pdf",
                    "xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    "xls": "application/vnd.ms-excel",
                    "csv": "text/csv",
                    "html": "text/html",
                    "xml": "application/xml",
                }.get(ext, "application/octet-stream")

                out_name = f"{output}_u{u['id']}_{datetime.utcfromtimestamp(f_ts).strftime('%Y%m%d')}.{ext}"
                logger.insert_file_blob(run_id, out_name, mime, content)

                bio = io.BytesIO(content)
                bio.name = out_name
                try:
                    dest_table = dest_table_for_template(template_id, resource_id)
                    logger.log_step(run_id, "choose_dest_table", "local",
                                    {"template_id": template_id, "dest_table": dest_table},
                                    200, True, {"ok": True}, None)
                    logger.import_tabular_to_sql(run_id, bio, table_name=dest_table)

                    # replicar por cliente se ativado
                    if split_by_client:
                        try:
                            replicated = logger.replicate_run_rows_to_client_dbs(run_id, dest_table, plate_col=plate_col, client_db_prefix=client_db_prefix)
                            logger.log_step(run_id, "replicate_rows", "local",
                                            {"dest_table": dest_table, "replicated_rows": replicated}, 200, True, {"ok": True}, None)
                        except Exception as e:
                            logger.log_step(run_id, "replicate_rows", "local",
                                            {"dest_table": dest_table}, 0, False, None, str(e))

                except Exception as e:
                    logger.log_step(run_id, "import_tabular_to_sql", "local",
                                    {"file": out_name}, 0, False, None, str(e))

        logger.finish_run(run_id, "4", None)
        logger.close()
        return output

    # ---------- MODO SIMPLES (um único report) ----------
    exec_params = {
        "reportResourceId": resource_id,
        "reportTemplateId": template_id,
        "reportObjectId": object_id,
        "reportObjectSecId": 0,
        "interval": {"from": from_ts, "to": to_ts, "flags": flags}
    }
    if remote_exec:
        exec_params["remoteExec"] = 1
    client.exec_report(exec_params)

    final_status = None
    if remote_exec:
        start = time.time()
        while True:
            st = client.get_report_status()
            final_status = str(st.get("status", ""))
            running = st.get("reportIsRunning")
            client._vprint(f"[status] status={final_status} running={running}")
            if final_status == "4":
                break
            if final_status == "8":
                logger.finish_run(run_id, final_status, "Falha no relatório (status=8)")
                raise RuntimeError("Relatório falhou no Wialon: status=8")
            if time.time() - start > timeout:
                logger.finish_run(run_id, final_status, "Timeout esperando relatório")
                raise TimeoutError("Timeout esperando relatório concluir")
            time.sleep(1.5)
        client.apply_report_result()
    else:
        final_status = "4"

    fmt_code = FORMAT_MAP.get(fmt.lower(), 8)
    exp_params = {"format": fmt_code, "compress": 0, "outputFileName": "Relatorio_Wialon"}
    content = client.export_result(exp_params)

    ext = EXT_BY_FORMAT.get(fmt_code, "bin")
    if not output.lower().endswith(f".{ext}"):
        output = f"{output}.{ext}"

    mime = {
        "pdf": "application/pdf",
        "xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        "xls": "application/vnd.ms-excel",
        "csv": "text/csv",
        "html": "text/html",
        "xml": "application/xml"
    }.get(ext, "application/octet-stream")

    logger.insert_file_blob(run_id, os.path.basename(output), mime, content)

    bio = io.BytesIO(content)
    bio.name = output  # para o pandas inferir o formato
    try:
        dest_table = dest_table_for_template(template_id, resource_id)
        logger.log_step(run_id, "choose_dest_table", "local",
                        {"template_id": template_id, "dest_table": dest_table},
                        200, True, {"ok": True}, None)
        logger.import_tabular_to_sql(run_id, bio, table_name=dest_table)

        # replicar por cliente se ativado
        if split_by_client:
            try:
                replicated = logger.replicate_run_rows_to_client_dbs(run_id, dest_table, plate_col=plate_col, client_db_prefix=client_db_prefix)
                logger.log_step(run_id, "replicate_rows", "local",
                                {"dest_table": dest_table, "replicated_rows": replicated}, 200, True, {"ok": True}, None)
            except Exception as e:
                logger.log_step(run_id, "replicate_rows", "local",
                                {"dest_table": dest_table}, 0, False, None, str(e))

    except Exception as e:
        logger.log_step(run_id, "import_tabular_to_sql", "local", {"file": output}, 0, False, None, str(e))

    logger.finish_run(run_id, final_status, None)
    logger.close()
    return output


def main():
    ap = argparse.ArgumentParser(description="Executa relatórios do Wialon e registra tudo em MySQL.")
    ap.add_argument("--base-url", default=DEFAULT_BASE_URL)
    ap.add_argument("--token")
    ap.add_argument("--sid")
    # MySQL
    ap.add_argument("--mysql-host", default="localhost")
    ap.add_argument("--mysql-user", default="root")
    ap.add_argument("--mysql-pass", default="")
    ap.add_argument("--mysql-db", default="Pontual_db")  # Default corrigido para consistência
    # Wialon report args
    ap.add_argument("--resource-id", type=int, required=True)
    ap.add_argument("--template-id", type=int, required=True)
    ap.add_argument("--object-id", type=int, required=True)
    ap.add_argument("--from", dest="from_value", required=True)
    ap.add_argument("--to", dest="to_value", required=True)
    ap.add_argument("--format", default="xlsx")
    ap.add_argument("--output", default="Relatorio_Wialon")
    ap.add_argument("--no-remote", action="store_true")
    ap.add_argument("--verbose", action="store_true")
    ap.add_argument("--timeout", type=int, default=300, help="Tempo máximo de espera do relatório")
    ap.add_argument("--http-timeout", type=int, default=300, help="Timeout de cada chamada HTTP (segundos)")
    # Flags modo amostragem
    ap.add_argument("--days", type=int, help="Quantos dias para trás a partir de --to")
    ap.add_argument("--plates-per-day", type=int, dest="plates_per_day", help="Quantidade de placas por dia")
    ap.add_argument("--unit-filter", default=None, help="Regex para filtrar nome/placa das unidades (opcional)")
    ap.add_argument("--seed", type=int, default=None, help="Semente p/ aleatoriedade reprodutível (opcional)")

    # --- NOVOS ARGS para replicação por cliente ---
    ap.add_argument("--split-by-client", action="store_true",
                    help="Além de salvar no DB central, replica as linhas em DBs separados por cliente com base na coluna de placa.")
    ap.add_argument("--plate-col", default="placa",
                    help="Nome da coluna que identifica a placa nas tabelas do relatório (default: placa).")
    ap.add_argument("--client-db-prefix", default="cliente_",
                    help="Prefixo a usar para os DBs por cliente (default: cliente_).")

    args = ap.parse_args()
    try:
        out = run_flow(
            base_url=args.base_url,
            token=args.token,
            sid=args.sid,
            mysql_host=args.mysql_host,
            mysql_user=args.mysql_user,
            mysql_pass=args.mysql_pass,
            mysql_db=args.mysql_db,
            resource_id=args.resource_id,
            template_id=args.template_id,
            object_id=args.object_id,
            from_value=args.from_value,
            to_value=args.to_value,
            fmt=args.format,
            output=args.output,
            remote_exec=not args.no_remote,
            verbose=args.verbose,
            timeout=args.timeout,
            http_timeout=args.http_timeout,
            days=args.days,
            plates_per_day=args.plates_per_day,
            unit_filter=args.unit_filter,
            seed=args.seed,
            split_by_client=args.split_by_client,
            plate_col=args.plate_col,
            client_db_prefix=args.client_db_prefix,
        )
        print(f"OK: Processo concluído. Saída principal: {out}")
    except Exception as e:
        print(f"ERRO: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
