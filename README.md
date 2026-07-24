# Iceberg Table Maintenance — Practical Guide

> Validates the **SBI Iceberg maintenance guide** (HTML) and exercises **Iceberg Spark procedures** on a CDP cluster.  
> CDP Private Cloud Base 7.3.1.600+ · Spark 3.5.4 · Iceberg 1.5.2

**Quick start:** [5. Default workflow — start to finish](#5-default-workflow--start-to-finish-recommended) (seed → pytest)

---

## 1. What is this project?

### One-line summary

This repo checks that the **operational HTML guide** for bank-style Iceberg maintenance is correct, and **automated integration tests** run the same procedures against a **practice table** on CDP.

### Why it matters

Continuous writes create many **small data files**. Queries slow down and **maintenance** (compaction, snapshot expiry, orphan cleanup) becomes necessary. This project ties the **guide**, **Spark SQL / procedures**, and **verification scripts** together so you can reproduce and test the workflow safely in a lab.

---

## 2. Iceberg in plain terms

Think of an Iceberg table as a **ledger**:

| Term | Plain meaning | In this repo |
|------|----------------|--------------|
| **Table** | One ledger book | `iceberg_compaction_test.txn_events` |
| **Data file** | Bundles of transaction rows on storage | `.parquet` under HDFS/Ozone |
| **Partition** | A drawer by business date | `business_date=2026-07-21` |
| **Snapshot** | A point-in-time view of the table | Created on each commit |
| **Manifest** | Index of which files belong where | Under `metadata/` |
| **Compaction** | Merging small files into fewer larger ones | `rewrite_data_files` |

### Table layout on storage

```
{table location}/
├── metadata/     ← snapshots, manifests (Iceberg metadata)
└── data/
    └── business_date=2026-07-21/
        └── *.parquet   ← row data (+ optional *-deletes.parquet)
```

**Two ways to inspect files**

- **Spark SQL** (e.g. `table.files`) — files **referenced by the current snapshot**
- **`hdfs dfs`** — **everything on disk** under the table location (older unreferenced files may remain until snapshot expiry)

---

## 3. Lab environment

| Storage | ID | Example URI |
|---------|-----|-------------|
| HDFS | NameService **`ns1`** | `hdfs://ns1/...` |
| Ozone | Service ID **`ozone1784520717`** | `ofs://ozone1784520717/...` |

**HDFS HA (standby NameNode warnings)**  
If Spark/YARN briefly hits a standby NameNode on `host:8020`, you may see `Operation category READ is not supported in state standby`. Ensure `.env` includes `HADOOP_CONF_DIR`, `HDFS_NAMESERVICE=ns1`, and `SPARK_CONF_spark_hadoop_fs_defaultFS=hdfs://ns1`, then `source scripts/load_env.sh` or run `kinit_cdp.sh` (which loads `cdp_client_env.sh`). Python entry points (`seed`, pytest) apply the same settings via `cdp_spark.py`.

**Practice table** (`.env` defaults)

| Item | Value |
|------|--------|
| Catalog | `spark_catalog` |
| Database | `iceberg_compaction_test` |
| Table | `txn_events` |
| Full name | `iceberg_compaction_test.txn_events` |
| Practice partition | `2026-07-21` (`business_date`) |
| Table location after seed (HDFS) | `hdfs://ns1/warehouse/tablespace/external/hive/iceberg_compaction_test.db/txn_events` |

> This lab uses the **external Hive warehouse** (`/warehouse/tablespace/external/hive/...`), not `/user/hive/warehouse/...`. Always set `TABLE_LOC` from the **Location** row in `DESCRIBE TABLE EXTENDED`.

### Python on the CDP edge node

| Command | Version | Use in this project? |
|---------|---------|----------------------|
| `python` | 2.7.18 | No |
| `python3` | 3.8.12 (parcel) | No (do not use for venv/pytest) |
| **`python3.11`** | **3.11.11** | **Yes — required** |

`.env` sets `PYTHON=python3.11`. `setup_venv.sh` and shell helpers use it.

```bash
python3.11 --version    # expect Python 3.11.11
source .venv/bin/activate
python --version        # Python 3.11.11 inside venv
```

---

## 4. Repository layout

```
spark-iceberg-compaction/
├── guide/              ← Customer HTML maintenance guide
├── spec/               ← Iceberg 1.5.2 procedure reference
├── scripts/            ← kinit, seed, Spark SQL wrapper, step runner
├── src/guide_validator/← Guide validation and SQL templates
├── tests/integration/  ← CDP integration tests (T1–T6)
└── docs/               ← Kerberos / Auto-TLS runbooks
```

| Script | Purpose |
|--------|---------|
| `scripts/kinit_cdp.sh` | Kerberos ticket |
| `scripts/cdp_client_env.sh` | HDFS HA / Hadoop conf (via load_env / kinit) |
| `scripts/seed_iceberg_table.py` | Build a “needs maintenance” practice table |
| `scripts/spark_sql_maintenance.sh` | Spark SQL with env + Iceberg settings |
| `scripts/run_step_with_verify.sh` | Run a guide step with before/after checks |
| `tests/integration/test_cdp_procedures.py` | Automated procedure tests |

---

## 5. Default workflow — start to finish (recommended)

This is the **standard way** to use the project.

For a repeatable **pre-maintenance** state, you **must seed the table before pytest**. **pytest does not create data.**

### Copy-paste sequence

```bash
cd ~/spark-iceberg-compaction

# ── One-time setup ──
cp .env.example .env
chmod +x scripts/*.sh
./scripts/setup_venv.sh          # creates .venv with python3.11

# ── Each full run ──
source scripts/load_env.sh
./scripts/kinit_cdp.sh
source .venv/bin/activate

# ★ Reset table to pre-maintenance state
python scripts/seed_iceberg_table.py --recreate
# without venv: python3.11 scripts/seed_iceberg_table.py --recreate

# (Optional) inject orphans for T3 dry-run demo
python scripts/inject_orphan_files.py --count 3 --age-days 10

# Safe integration tests (T1–T5)
pytest tests/integration/ -m "cdp and not destructive" -v
```

**6 passed** means non-destructive maintenance procedures (T1–T5) succeeded on CDP.

### What each step does

| Step | Command | Effect |
|------|---------|--------|
| 1 | `kinit_cdp.sh` | Kerberos login |
| 2 | `seed --recreate` | Drop/recreate table with ~20 small DATA files, etc. |
| 3 | `inject_orphan_files` (optional) | Orphans for T3 dry-run |
| 4 | `pytest` | T1–T5 validation (**T4/T5 modify the table**) |

### Expected metrics right after seed

| Metric | Approximate |
|--------|-------------|
| Logical rows | ~120,000 |
| Snapshots | ~23 |
| DATA files (partition 2026-07-21) | ~20 |
| Position delete files | ~2 |

### Resetting after tests

After pytest, T4 (manifests) and T5 (compaction) have changed the table. To demo again from scratch:

```bash
python scripts/seed_iceberg_table.py --recreate
pytest tests/integration/ -m "cdp and not destructive" -v
```

### Including T6 (optional)

Set `CDP_ALLOW_DESTRUCTIVE=true` in `.env`, then:

```bash
pytest tests/integration/ -m cdp -v
```

> For **same-day** expire/orphan effects on a fresh seed, see `EXPIRE_OLDER_THAN` and `ORPHAN_OLDER_THAN` in `.env.example`. Guide defaults (30d / 7d) rarely affect brand-new snapshots.

### What pytest does *not* do

| Goal | How |
|------|-----|
| Pre-maintenance data | `seed --recreate` (**required**) |
| Live orphan delete | `run_step_with_verify.sh step7_orphan_delete` |
| Metadata TBLPROPERTIES | `run_step_with_verify.sh step6_metadata_properties` |
| CSV before/after metrics | `capture_metrics.sh` + `compare_metrics.sh` |

Full operations runbook: [docs/CDP_Kerberos_AutoTLS_Maintenance_Runbook.md](docs/CDP_Kerberos_AutoTLS_Maintenance_Runbook.md)

---

## 6. First-time setup

### 6-1. Configuration

```bash
cd ~/spark-iceberg-compaction
cp .env.example .env
# edit .env if needed
```

### 6-2. Kerberos

```bash
chmod +x scripts/*.sh
./scripts/kinit_cdp.sh
```

### 6-3. Python 3.11 virtualenv

Do **not** use system `python` (2.7) or `python3` (3.8) for this project.

```bash
./scripts/setup_venv.sh

# Manual alternative
python3.11 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip setuptools wheel
python -m pip install -e ".[dev]"
python --version
```

> `kinit_cdp.sh` works without venv.  
> `spark_sql_maintenance.sh` falls back to **PySpark** when the CDP `spark-sql` CLI is missing (venv recommended).  
> `seed`, `pytest`, `validate-guide` — use venv `python` (3.11), or invoke `python3.11` explicitly.

### 6-4. Seed details

Same as [§5](#5-default-workflow--start-to-finish-recommended). Always start demos from seed.

```bash
python scripts/seed_iceberg_table.py --recreate
# optional: --batches 30 --rows-per-batch 20000
```

The script prints a snapshot/file summary when finished.

---

## 7. Automated tests (pytest) — T1 through T6

Run [§5](#5-default-workflow--start-to-finish-recommended) **`seed --recreate`** before pytest.

```bash
source .venv/bin/activate

pytest tests/integration/ -m "cdp and not destructive" -v

# T6 included — requires CDP_ALLOW_DESTRUCTIVE=true
pytest tests/integration/ -m cdp -v
```

### Test map

| Test | Name | What it checks | Risk |
|------|------|----------------|------|
| **T1** | Spark connectivity | Session and catalog | Safe |
| **T2** | Table metadata | Iceberg provider, `.files` | Safe |
| **T3** | Orphan dry-run | Lists orphans only (`dry_run => true`) | Safe |
| **T4** | Manifest rewrite | Manifest maintenance | Moderate |
| **T5** | Data file compaction | Bin-pack partition 2026-07-21 | Moderate |
| **T6** | Snapshot / delete maintenance | Expire + position-delete rewrite | **Destructive** |

### Code locations

- Fixtures: `tests/integration/conftest.py`
- Tests: `tests/integration/test_cdp_procedures.py`
- SQL templates: `src/guide_validator/template_renderer.py`

---

## 8. Running Spark SQL

Do **not** run bare `spark-sql` / `spark3-sql` on the edge node without project env. Use the wrapper:

| Use | Do this | Avoid |
|-----|---------|--------|
| SQL | `./scripts/spark_sql_maintenance.sh` | Raw `spark-sql` without Kerberos/TLS/Iceberg HA |
| PySpark lab | Wrapper + venv (auto fallback) | `.venv/bin/spark-sql` shim |
| Load data | `python scripts/seed_iceberg_table.py` | Large INSERT-only SQL for seed |

If the CDP CLI is missing, stderr shows  
`NOTE: using PySpark SQL runner (same settings as seed/pytest).` — **expected**.

---

### 8-1. Before each session

```bash
cd ~/spark-iceberg-compaction
source scripts/load_env.sh
./scripts/kinit_cdp.sh
source .venv/bin/activate

# optional: fresh pre-maintenance state
python scripts/seed_iceberg_table.py --recreate
```

Default table (`.env`):

| Item | Value |
|------|--------|
| Catalog | `spark_catalog` |
| Table | `iceberg_compaction_test.txn_events` |
| Partition | `business_date = 2026-07-21` |

---

### 8-2. Three ways to run SQL

All paths use the same script (YARN client mode). `SELECT` prints a table; `CALL` prints procedure output.

#### (1) Inline — `-e`

```bash
./scripts/spark_sql_maintenance.sh -e "SELECT 1;"
./scripts/spark_sql_maintenance.sh -e "SELECT current_catalog(), version();"
```

Multiple statements (semicolon-separated) are supported in the PySpark runner:

```bash
./scripts/spark_sql_maintenance.sh -e "
USE spark_catalog;
SELECT count(*) FROM iceberg_compaction_test.txn_events;
"
```

#### (2) File — `-f`

```bash
cat > /tmp/check_files.sql <<'SQL'
USE spark_catalog;

SELECT content, count(*)
FROM iceberg_compaction_test.txn_events.files
GROUP BY content;
SQL

./scripts/spark_sql_maintenance.sh -f /tmp/check_files.sql
```

#### (3) Heredoc (multi-line `CALL`)

```bash
./scripts/spark_sql_maintenance.sh <<'SQL'
USE spark_catalog;

CALL spark_catalog.system.rewrite_manifests(
  table => 'iceberg_compaction_test.txn_events',
  use_caching => false
);
SQL
```

> Closing `SQL` must be at **column 0** (no leading spaces).

#### (4) Interactive REPL

Argument-less `./scripts/spark_sql_maintenance.sh` opens the CDP REPL when available. On this lab, prefer `-e`, `-f`, or heredoc. Set `SPARK_SQL_BACKEND=pyspark` in `.env` to force PySpark only.

---

### 8-3. Guide steps via shell — `run_step_with_verify.sh`

```bash
source scripts/load_env.sh
./scripts/kinit_cdp.sh
source .venv/bin/activate

./scripts/run_step_with_verify.sh step2_rewrite_data_files run
```

| Step ID | Guide action |
|---------|----------------|
| `step2_rewrite_data_files` | T5 — compact data files |
| `step3_rewrite_position_delete_files` | Compact position deletes |
| `step4_rewrite_manifests` | T4 — rewrite manifests |
| `step5_expire_snapshots` | Expire snapshots |
| `step6_metadata_properties` | Metadata TBLPROPERTIES |
| `step7_orphan_dry_run` | T3 — orphan list (dry-run) |
| `step7_orphan_delete` | Delete orphans (**caution**) |

Modes: `pre` · `post` · `run` (pre → procedure → post → compare)

---

### 8-4. Step-by-step SQL (manual)

Use any method from [§8-2](#8-2-three-ways-to-run-sql). Examples use `-e` or heredoc.

#### Step 0 — Table location

```bash
./scripts/spark_sql_maintenance.sh -e "
USE spark_catalog;
DESCRIBE TABLE EXTENDED spark_catalog.iceberg_compaction_test.txn_events;
"
```

Copy **Location**, then on HDFS (this lab’s seed path):

```bash
export TABLE_LOC="hdfs://ns1/warehouse/tablespace/external/hive/iceberg_compaction_test.db/txn_events"
hdfs dfs -ls "${TABLE_LOC}"
hdfs dfs -ls "${TABLE_LOC}/data/business_date=2026-07-21"
```

> `DESCRIBE DETAIL` is **not** supported on CDP Spark 3.5; use `DESCRIBE TABLE EXTENDED`. The PySpark runner shows up to 1000 rows for `DESCRIBE`/`SHOW` so Location is visible.

#### After seed — “messy” baseline

```bash
./scripts/spark_sql_maintenance.sh -e "
USE spark_catalog;
SELECT count(*) FROM iceberg_compaction_test.txn_events;
SELECT content, count(*) FROM iceberg_compaction_test.txn_events.files GROUP BY content;
SELECT count(*) FROM iceberg_compaction_test.txn_events.snapshots;
"
```

Expect ~120,000 rows; `content=0` → ~20 DATA files, `content=1` → ~2 delete files; ~23 snapshots.

> On CDP Spark 3.5, `.files.content` is typically **integer**: `0` = DATA, `1` = POSITION_DELETES. Use `content = 0` in filters (not the string `'DATA'`).

#### T1 — Connectivity

```bash
./scripts/spark_sql_maintenance.sh -e "SELECT current_catalog(), version();"
```

#### T2 — Iceberg table and files

```bash
./scripts/spark_sql_maintenance.sh -e "
USE spark_catalog;
DESCRIBE TABLE EXTENDED spark_catalog.iceberg_compaction_test.txn_events;
SELECT file_path, file_size_in_bytes, content
FROM iceberg_compaction_test.txn_events.files LIMIT 5;
"
```

Confirm `Provider = iceberg`.

#### T3 — Orphan candidates (dry-run)

```bash
./scripts/spark_sql_maintenance.sh <<'SQL'
CALL spark_catalog.system.remove_orphan_files(
  table => 'iceberg_compaction_test.txn_events',
  older_than => timestamp '2000-01-01 00:00:00',
  dry_run => true
);
SQL
```

Empty output is normal unless you ran `inject_orphan_files.py`.

#### T4 — Manifest rewrite

**Before:**

```bash
./scripts/spark_sql_maintenance.sh -e "
SELECT count(*) FROM iceberg_compaction_test.txn_events.manifests;
"
```

**Run:**

```bash
./scripts/spark_sql_maintenance.sh <<'SQL'
CALL spark_catalog.system.rewrite_manifests(
  table => 'iceberg_compaction_test.txn_events',
  use_caching => false
);
SQL
```

**After:**

```bash
./scripts/spark_sql_maintenance.sh -e "
SELECT count(*) FROM iceberg_compaction_test.txn_events.manifests;
SELECT snapshot_id, made_current_at
FROM iceberg_compaction_test.txn_events.history
ORDER BY made_current_at DESC LIMIT 3;
"
```

#### T5 — Data file compaction (primary maintenance)

**Before:**

```bash
./scripts/spark_sql_maintenance.sh -e "
SELECT count(*) AS files,
       cast(avg(file_size_in_bytes) AS bigint) AS avg_bytes
FROM iceberg_compaction_test.txn_events.files
WHERE content = 0
  AND partition.business_date = DATE '2026-07-21';
"
```

**Run** (use `make_date` in `where` on CDP):

```bash
./scripts/spark_sql_maintenance.sh <<'SQL'
CALL spark_catalog.system.rewrite_data_files(
  table => 'iceberg_compaction_test.txn_events',
  strategy => 'binpack',
  where => 'business_date = make_date(2026, 7, 21)',
  options => map(
    'target-file-size-bytes', '536870912',
    'min-input-files', '5',
    'max-concurrent-file-group-rewrites', '2',
    'max-file-group-size-bytes', '21474836480',
    'partial-progress.enabled', 'false'
  )
);
SQL
```

**After:**

```bash
./scripts/spark_sql_maintenance.sh -e "
SELECT count(*) AS files,
       cast(avg(file_size_in_bytes) AS bigint) AS avg_bytes
FROM iceberg_compaction_test.txn_events.files
WHERE content = 0
  AND partition.business_date = DATE '2026-07-21';
SELECT count(*) FROM iceberg_compaction_test.txn_events
WHERE business_date = DATE '2026-07-21';
"
```

| | Before | After |
|--|--------|-------|
| Active DATA files (Spark `.files`) | ~20 | ~1–5 |
| Row count | ~120k | **unchanged** |

> **HDFS file count** may stay high until `expire_snapshots` drops unreferenced files. Trust `.files` for active file counts.

#### T6 — (optional) Snapshots and position deletes

```bash
./scripts/spark_sql_maintenance.sh <<'SQL'
CALL spark_catalog.system.expire_snapshots(
  table => 'iceberg_compaction_test.txn_events',
  older_than => timestamp '2000-01-01 00:00:00',
  retain_last => 20,
  max_concurrent_deletes => 4
);

CALL spark_catalog.system.rewrite_position_delete_files(
  table => 'iceberg_compaction_test.txn_events',
  options => map(
    'min-input-files', '2',
    'max-concurrent-file-group-rewrites', '2',
    'max-file-group-size-bytes', '21474836480'
  )
);
SQL
```

> On production or shared labs: approvals, backups, and `CDP_ALLOW_DESTRUCTIVE=true` before T6. To reclaim HDFS space in a **test** lab, lower `retain_last` (e.g. `1`) only after understanding snapshot retention impact.

---

### 8-5. HDFS checks (pair with Spark SQL)

```bash
export TABLE_LOC="hdfs://ns1/warehouse/tablespace/external/hive/iceberg_compaction_test.db/txn_events"

hdfs dfs -ls "${TABLE_LOC}/metadata"
hdfs dfs -count -h "${TABLE_LOC}/data/business_date=2026-07-21"
hdfs dfs -ls -h "${TABLE_LOC}/data/business_date=2026-07-21"
```

For Ozone-backed tables, Location may be `ofs://ozone1784520717/...`.

---

### 8-6. Common log messages

| Message | Meaning |
|---------|---------|
| `NOTE: using PySpark SQL runner` | PySpark fallback — **OK** |
| `Picked up JAVA_TOOL_OPTIONS` | Auto-TLS truststore — **OK** |
| YARN application ID lines | Client-mode submission — **OK** |
| `make_date(2026, 7, 21)` | CDP-safe date literal in `CALL` `where` clauses |

---

## 9. Manual verification checklist (summary)

> Detailed CLI flows: [§8](#8-running-spark-sql).  
> This section is a **short checklist** for the post-seed, pre-pytest state from [§5](#5-default-workflow--start-to-finish-recommended).

### Common prep

```bash
cd ~/spark-iceberg-compaction
source scripts/load_env.sh
./scripts/kinit_cdp.sh
source .venv/bin/activate
./scripts/spark_sql_maintenance.sh -e "SELECT 1;"
```

### Step 0 — Where is the table on disk?

**Spark SQL:** `DESCRIBE TABLE EXTENDED` → **Location** row.

**HDFS:**

```bash
export TABLE_LOC="hdfs://ns1/warehouse/tablespace/external/hive/iceberg_compaction_test.db/txn_events"
hdfs dfs -ls "${TABLE_LOC}"
hdfs dfs -ls "${TABLE_LOC}/metadata"
hdfs dfs -ls "${TABLE_LOC}/data/business_date=2026-07-21"
```

### Post-seed baseline

Spark: row count ~120k; `GROUP BY content` → ~20 / ~2; snapshot count ~23.  
HDFS: many small parquet files under the partition path.

### T1–T6

Follow the SQL blocks in [§8-4](#8-4-step-by-step-sql-manual) and compare Spark `.files` vs `hdfs dfs` after T5/T6.

### T6 via pytest

```bash
pytest tests/integration/ -m "cdp and destructive" -v
```

---

## 10. Validate the HTML guide (no cluster)

```bash
validate-guide --skip-links
pytest tests/ -m "not cdp and not network" -v
```

---

## 11. Production-oriented docs

- [docs/CDP_Kerberos_AutoTLS_Maintenance_Runbook.md](docs/CDP_Kerberos_AutoTLS_Maintenance_Runbook.md)
- [docs/CDP_Kerberos_Keytab_Guide.md](docs/CDP_Kerberos_Keytab_Guide.md)

Example step run:

```bash
./scripts/run_step_with_verify.sh step2_rewrite_data_files run
```

Capture metrics to CSV:

```bash
export MAINTENANCE_RUN_ID=demo_$(date +%Y%m%d_%H%M)
./scripts/capture_metrics.sh before_t5
# run T5 ...
./scripts/capture_metrics.sh after_t5
```

---

## 12. Maintenance order (matches the guide)

```
Pre-checks
  → Compact data files (rewrite_data_files)           ← T5
  → Compact position deletes (conditional)            ← T6
  → Rewrite manifests (conditional)                   ← T4
  → Expire snapshots                                  ← T6
  → Orphan cleanup (separate window; dry-run first)   ← T3
```

---

## 13. FAQ

**Q. Standby NameNode / `8020` / `READ is not supported` during seed or Spark startup?**  
A. Typical HDFS HA failover noise. Verify `.env`: `HADOOP_CONF_DIR=/etc/hadoop/conf`, `HDFS_NAMESERVICE=ns1`, `SPARK_CONF_spark_hadoop_fs_defaultFS=hdfs://ns1`, then `source scripts/load_env.sh`. `JAVA_TOOL_OPTIONS` for the truststore is expected.

**Q. `spark-sql not found` or `SparkSQLCLIDriver` errors?**  
A. The wrapper switches to **PySpark** (`spark_sql_maintenance.py`) with the same settings as seed/pytest. `NOTE: using PySpark SQL runner` on stderr is OK. Set `SPARK_HOME` to force the CDP CLI, or `SPARK_SQL_BACKEND=pyspark` to force PySpark.

**Q. Can I use `python` or `python3`?**  
A. On this edge node, `python` is 2.7 and `python3` is 3.8. Use **`python3.11`** and `.venv` per `.env`.

**Q. Does pytest create the practice table?**  
A. **No.** Run `seed --recreate` first ([§5](#5-default-workflow--start-to-finish-recommended)).

**Q. Six pytest passes — ready for production?**  
A. That means the **practice table** workflow passed. Production still needs change control, Ranger policies, YARN queues, and retention policies.

**Q. Spark `.files` vs `hdfs dfs` counts differ?**  
A. Expected. SQL reflects **current snapshot** references; HDFS lists **all objects on disk** until snapshot expiry removes unreferenced files.

**Q. Why `make_date(2026, 7, 21)` in `CALL`?**  
A. Avoids fragile quoting of date literals in CDP `CALL` statements.

**Q. Why does `content = 'DATA'` return zero rows?**  
A. On CDP Spark 3.5 / Iceberg, `.files.content` is often numeric. Filter with **`content = 0`** for DATA files.

**Q. Updated the HTML guide?**  
A. Replace `guide/SBI_Iceberg_Compaction_Maintenance_Guide_final_EN.html`, then run `validate-guide --skip-links`.

---

## 14. License

Cloudera Professional Services — internal tooling for the SBI CDP engagement.
