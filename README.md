# SBI Iceberg Compaction Guide Validator

Validation project for the **SBI Iceberg Compaction & Maintenance Operational Guide** (CDP Private Cloud Base 7.3.1.600+, Spark 3.5.4, Iceberg 1.5.2).

This project validates that the HTML guide's SQL/CALL examples, table properties, operational policies, and reference links are consistent with **Apache Iceberg 1.5.2** Spark Procedures documentation. Optional integration tests run the same procedures against a CDP Spark cluster.

## Customer runbook (Kerberos + Auto-TLS)

For step-by-step maintenance execution on a **Kerberos + Auto-TLS** CDP cluster (principal example: `systest@QE-INFRA-AD.CLOUDERA.COM`), see:

**[docs/CDP_Kerberos_AutoTLS_Maintenance_Runbook.md](docs/CDP_Kerberos_AutoTLS_Maintenance_Runbook.md)**

Covers the guide execution order with **step-wise metrics capture and comparison** (pre/post data verification).

Shell helpers:

```bash
cp .env.example .env   # set KERBEROS_*, TRUSTSTORE_*, TARGET_*
chmod +x scripts/*.sh

export MAINTENANCE_RUN_ID=$(date -u +%Y%m%d_%H%M%S)
./scripts/kinit_cdp.sh
./scripts/capture_metrics.sh step1_baseline
./scripts/run_step_with_verify.sh step2_rewrite_data_files run   # pre → procedure → post → compare
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

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"

# Text report (offline — skips URL checks)
validate-guide --skip-links

# JSON report
validate-guide --skip-links --format json

# Include reference URL checks
validate-guide

# pytest (static only, no network/CDP)
pytest tests/ -m "not cdp and not network" -v
```

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
pip install -e ".[cdp]"

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
