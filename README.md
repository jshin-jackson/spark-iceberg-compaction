# SBI Iceberg Compaction Guide Validator

Validation project for the **SBI Iceberg Compaction & Maintenance Operational Guide** (CDP Private Cloud Base 7.3.1.600+, Spark 3.5.4, Iceberg 1.5.2).

This project validates that the HTML guide's SQL/CALL examples, table properties, operational policies, and reference links are consistent with **Apache Iceberg 1.5.2** Spark Procedures documentation. Optional integration tests run the same procedures against a CDP Spark cluster.

## Customer runbook (Kerberos + Auto-TLS)

For step-by-step maintenance execution on a **Kerberos + Auto-TLS** CDP cluster (principal example: `systest@QE-INFRA-AD.CLOUDERA.COM`), see:

**[docs/CDP_Kerberos_AutoTLS_Maintenance_Runbook.md](docs/CDP_Kerberos_AutoTLS_Maintenance_Runbook.md)** · **[Keytab guide](docs/CDP_Kerberos_Keytab_Guide.md)** (`/cdep/keytabs/systest.keytab`)

Covers the guide execution order with **step-wise metrics capture and comparison** (pre/post data verification).

Shell helpers:

```bash
cp .env.example .env
chmod +x scripts/*.sh

./scripts/kinit_cdp.sh              # .env 자동 로드 + kinit
# interactive shell: source scripts/load_env.sh
./scripts/run_step_with_verify.sh step2_rewrite_data_files run
```

## What gets validated

| Layer | Checks |
|-------|--------|
| **Procedures** | `rewrite_data_files`, `rewrite_position_delete_files`, `rewrite_manifests`, `expire_snapshots`, `remove_orphan_files` — args, options, forbidden `where` on table-scope procedures |
| **Properties** | `write.target-file-size-bytes`, metadata JSON retention pair |
| **Policy** | Execution order, version baseline, checklist, partition vs table scope |
| **Links** | §11 reference URLs (optional, requires network) |
| **CDP integration** | Tiered procedure execution on a dedicated test table |

## Quick start (static validation)

CDP edge node에서는 **`python3`** 를 사용하십시오 (`python -m venv`는 venv 모듈 없음).

```bash
# 권장: setup 스크립트
chmod +x scripts/setup_venv.sh
./scripts/setup_venv.sh

# 또는 수동 (CDP edge: pip upgrade 필수)
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip setuptools wheel
python -m pip install -e ".[dev]"

# Text report (offline — skips URL checks)
validate-guide --skip-links

# JSON report
validate-guide --skip-links --format json

# Include reference URL checks
validate-guide

# pytest (static only, no network/CDP)
pytest tests/ -m "not cdp and not network" -v
```

> Maintenance shell scripts (`kinit_cdp.sh`, `spark_sql_maintenance.sh`, …)는 **venv 없이** 동작합니다.  
> Python 도구(`validate-guide`, `pytest`, `capture_metrics.py`)만 venv가 필요합니다.

## CDP integration tests

Run on a **CDP edge node** with YARN client access and a dedicated maintenance test table (not PROD).

### 1. Configure environment

```bash
cp .env.example .env
# Edit .env: catalog, TEST_DATABASE, TEST_TABLE, partition filter, Spark configs
```

| Variable | Description |
|----------|-------------|
| `CDP_SPARK_MASTER` | `yarn` or Spark master URL |
| `KERBEROS_PRINCIPAL` | e.g. `systest@QE-INFRA-AD.CLOUDERA.COM` |
| `KERBEROS_KEYTAB` | Path to service/user keytab |
| `TRUSTSTORE_PATH` | Auto-TLS JKS/PEM truststore (from CM) |
| `ICEBERG_CATALOG` | Catalog name (e.g. `spark_catalog`) |
| `TEST_DATABASE` | Sandbox database |
| `TEST_TABLE` | Partitioned Iceberg test table |
| `TEST_PARTITION_FILTER` | `where` clause for `rewrite_data_files` |
| `SPARK_CONF_*` | Spark config (underscores → dots) |
| `CDP_ALLOW_DESTRUCTIVE` | `true` to enable T6 tests |
| `CDP_SKIP_KERBEROS` | `true` to skip kinit in pytest (ticket already held) |

### 2. Minimum Spark / Iceberg config

```
spark.sql.extensions=org.apache.iceberg.spark.extensions.IcebergSparkSessionExtensions
spark.sql.catalog.spark_catalog=org.apache.iceberg.spark.SparkCatalog
spark.sql.catalog.spark_catalog.type=hive
```

Map these in `.env` using the `SPARK_CONF_` prefix (see `.env.example`).

### 3. Run integration tests

```bash
python3 -m venv .venv   # or: ./scripts/setup_venv.sh
source .venv/bin/activate
python -m pip install --upgrade pip setuptools wheel
python -m pip install -e ".[cdp]"

# Safe tiers only (T1–T5: catalog, metadata, dry-run orphan, rewrite_manifests, rewrite_data_files)
pytest tests/integration/ -m "cdp and not destructive" -v

# Include destructive tests (requires CDP_ALLOW_DESTRUCTIVE=true)
pytest tests/integration/ -m cdp -v
```

### Test tiers

| Tier | Test | Safety |
|------|------|--------|
| T1 | SparkSession active | Safe |
| T2 | `SHOW TABLES`, `DESCRIBE`, `.files` metadata | Safe |
| T3 | `remove_orphan_files(dry_run=true)` | Safe |
| T4 | `rewrite_manifests(use_caching=false)` | Medium |
| T5 | `rewrite_data_files` with partition `where` | Medium |
| T6 | `expire_snapshots`, `rewrite_position_delete_files` | Destructive (opt-in) |

## Reproducible test scenario (seed data)

The guide's procedures only do something when the table is in the "bad" state each
one fixes. `scripts/seed_iceberg_table.py` builds a format-v2, merge-on-read,
`business_date`-partitioned table (`iceberg_compaction_test.txn_events`) and
deliberately creates those states with plain Spark (no external dependency):

| Guide section | Reproduced by |
|---------------|---------------|
| §3 `rewrite_data_files` | many small files in one partition (N small append commits) |
| §4 `rewrite_position_delete_files` | position deletes via `DELETE`/`UPDATE` (merge-on-read) |
| §5 `rewrite_manifests` | manifests accumulated from many commits |
| §6 `expire_snapshots` | many snapshots (see override note below) |
| §8 `remove_orphan_files` | `scripts/inject_orphan_files.py` writes unreferenced parquet |

```bash
source scripts/load_env.sh      # loads .env (TARGET_/TEST_ = iceberg_compaction_test.txn_events)
./scripts/kinit_cdp.sh

# 1) create + seed (20 small batches by default) and make position deletes
python scripts/seed_iceberg_table.py --recreate

# 2) (optional) inject orphan files aged 10 days so guide's -7d catches them
python scripts/inject_orphan_files.py --count 3 --age-days 10

# 3) run each step with pre/post verification
./scripts/run_step_with_verify.sh step2_rewrite_data_files run
./scripts/run_step_with_verify.sh step3_rewrite_position_delete_files run
./scripts/run_step_with_verify.sh step4_rewrite_manifests run
./scripts/run_step_with_verify.sh step6_metadata_properties run
./scripts/run_step_with_verify.sh step5_expire_snapshots run
./scripts/run_step_with_verify.sh step7_orphan_dry_run run
./scripts/run_step_with_verify.sh step7_orphan_delete run   # after approving dry-run
```

> **Same-day reproduction caveat.** The guide's real values (`expire_snapshots`
> `older_than => -30d, retain_last => 20`; `remove_orphan_files older_than => -7d`)
> will **not** expire freshly-seeded snapshots or catch brand-new orphans. To see
> those two steps actually change something on a just-seeded table, set the test
> overrides in `.env` and restore the guide values for real operations:
>
> ```bash
> EXPIRE_OLDER_THAN="CURRENT_TIMESTAMP"
> EXPIRE_RETAIN_LAST=1
> ORPHAN_OLDER_THAN="CURRENT_TIMESTAMP"
> ```
>
> `inject_orphan_files.py` backdates file mtime (default 10 days), so orphan
> cleanup works with the guide's real `-7d` value without any override.

## Updating the guide

1. Replace `guide/SBI_Iceberg_Compaction_Maintenance_Guide_reviewed.html`
2. Run `validate-guide --skip-links`
3. Run `pytest tests/ -m "not cdp and not network" -v`

## Project layout

```
guide/                          # HTML guide under validation
spec/                           # Iceberg 1.5.2 procedure & property specs
src/guide_validator/            # Parsers, validators, CDP helpers
scripts/validate_guide.py       # CLI wrapper
scripts/seed_iceberg_table.py   # Create + seed test table (reproduce compaction states)
scripts/inject_orphan_files.py  # Write unreferenced files for remove_orphan_files
scripts/run_step_with_verify.sh # Per-step procedure + pre/post metrics compare
tests/unit/                     # Unit tests
tests/integration/              # CDP Spark integration tests
```

## Mapping to guide §10 checklist

| Checklist item | Validated by |
|----------------|--------------|
| Iceberg SQL extension, catalog, Ranger, storage | CDP T1–T2 (manual Ranger review) |
| Format version, delete type, files/snapshots scale | CDP T2 metadata queries |
| Partition lock / no overlapping jobs | Policy validator + operational runbook |
| Table-scope maintenance windows | Policy validator (table-scope procedures) |
| YARN queue / executor limits | Manual CDP config (not automated) |
| Pilot partition metrics | CDP T5 |
| Orphan dry-run approval | Static validator (2-step pattern) + CDP T3 |

## License

Internal Cloudera Professional Services tooling for the SBI CDP engagement.
