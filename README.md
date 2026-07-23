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

## CDP verification walkthrough (Spark SQL & storage)

Iceberg를 처음 접하는 분도 따라올 수 있도록, **integration test tier(T1–T6)** 마다 Spark SQL로
논리·메타데이터를 확인하고, **HDFS / Ozone**에서 실제 파일·폴더를 확인하는 방법을 정리했습니다.

별도 스크립트 없이, edge node에서 **명령을 복사해 실행**하면 됩니다.

### 이 lab의 클러스터 식별자

| Storage | 식별자 | URI 예시 |
|---------|--------|----------|
| HDFS HA | NameService **`ns1`** | `hdfs://ns1/...` |
| Ozone | Service ID **`ozone1784520717`** | `ofs://ozone1784520717/...` |

테이블이 HDFS warehouse에 있으면 `hdfs://ns1/...`, Ozone bucket에 있으면
`ofs://ozone1784520717/...`로 시작합니다. **어느 쪽인지는 아래 Location 조회 결과가
기준**이며, 예시 경로는 seed 기본값(`iceberg_compaction_test.txn_events`) 기준입니다.

### 사전 준비

```bash
cd ~/spark-iceberg-compaction
source scripts/load_env.sh
./scripts/kinit_cdp.sh
```

Spark SQL은 프로젝트 wrapper로 실행합니다 (Kerberos · Iceberg catalog 설정 포함):

```bash
./scripts/spark_sql_maintenance.sh -e "SELECT current_catalog();"
```

아래 SQL 블록 전체를 `-e "..."` 인자로 넘기거나, `spark-sql` 대화형 세션에 붙여 넣으면 됩니다.

**대상 테이블 (`.env` 기본값)**

| 항목 | 값 |
|------|-----|
| Catalog | `spark_catalog` |
| Database | `iceberg_compaction_test` |
| Table | `txn_events` |
| Full name | `iceberg_compaction_test.txn_events` |
| 파티션 | `business_date = 2026-07-21` |

### Iceberg 테이블 폴더 구조 (개념)

Location 아래 대략 다음과 같이 구성됩니다.

```
{Location}/
├── metadata/          ← snapshot·manifest·*.metadata.json (Iceberg “두뇌”)
└── data/
    └── business_date=2026-07-21/
        ├── *.parquet  ← DATA 파일
        └── *.parquet  ← delete 파일 (merge-on-read)
```

- **Spark SQL** → Iceberg 메타데이터 뷰(`.files`, `.snapshots` 등)로 “현재 snapshot이
  참조하는” 파일을 봅니다.
- **hdfs / ozone** → 디스크에 실제로 존재하는 모든 파일을 봅니다. compaction 직후에는
  **이전 snapshot이 참조하는 old 파일**이 expire 전까지 disk에 남을 수 있습니다.

### 0단계 — 테이블 Location 확인 (모든 tier 공통)

먼저 warehouse 경로를 확인합니다. 이후 HDFS/Ozone 명령의 `{TABLE_LOC}` 자리에 넣습니다.

**Spark SQL**

```sql
USE spark_catalog;

DESCRIBE TABLE EXTENDED spark_catalog.iceberg_compaction_test.txn_events;
-- 출력에서 col_name = Location 인 행의 data_type 값이 {TABLE_LOC}

SHOW TBLPROPERTIES iceberg_compaction_test.txn_events;
```

**HDFS warehouse 예시** (Hive 기본 경로 패턴 — Location이 `hdfs://ns1/...`일 때)

```bash
# DESCRIBE 결과를 복사해 사용
export TABLE_LOC="hdfs://ns1/user/hive/warehouse/iceberg_compaction_test.db/txn_events"

hdfs dfs -ls "${TABLE_LOC}"
hdfs dfs -ls "${TABLE_LOC}/metadata"
hdfs dfs -ls "${TABLE_LOC}/data"
hdfs dfs -ls "${TABLE_LOC}/data/business_date=2026-07-21"
hdfs dfs -du -h "${TABLE_LOC}"
```

**Ozone 예시** (Location이 `ofs://ozone1784520717/...`일 때)

```bash
export TABLE_LOC="ofs://ozone1784520717/volume/bucket/path/txn_events"

hdfs dfs -ls "${TABLE_LOC}"
hdfs dfs -ls "${TABLE_LOC}/metadata"
hdfs dfs -ls "${TABLE_LOC}/data"
hdfs dfs -du -h "${TABLE_LOC}"
```

> Ozone 경로도 CDP에서는 `hdfs dfs`로 접근하는 경우가 많습니다. `ofs://` URI 그대로
> `-ls` / `-du`에 사용하세요.

---

### Seed 직후 — `seed_iceberg_table.py` 결과 확인

pytest 전에 seed로 “유지보수가 필요한 상태”를 만듭니다.

```bash
python scripts/seed_iceberg_table.py --recreate
```

**Spark SQL — seed 요약과 동일 지표**

```sql
USE spark_catalog;

-- 논리 row 수
SELECT count(*) AS row_cnt
FROM iceberg_compaction_test.txn_events;

-- 파일 종류별 개수 (seed 직후 대략: DATA ~20, POSITION_DELETES ~2)
SELECT content, count(*) AS file_cnt, sum(file_size_in_bytes) AS bytes
FROM iceberg_compaction_test.txn_events.files
GROUP BY content;

SELECT count(*) AS snapshot_cnt FROM iceberg_compaction_test.txn_events.snapshots;
SELECT count(*) AS manifest_cnt FROM iceberg_compaction_test.txn_events.manifests;

-- 대상 파티션 DATA 파일 (T5 compaction 전 ≈ 20개)
SELECT count(*) AS data_files_in_partition,
       cast(avg(file_size_in_bytes) AS bigint) AS avg_bytes
FROM iceberg_compaction_test.txn_events.files
WHERE content = 'DATA'
  AND partition.business_date = DATE '2026-07-21';
```

**HDFS / Ozone — 물리 파일**

```bash
hdfs dfs -count -h "${TABLE_LOC}/data/business_date=2026-07-21"
hdfs dfs -ls -h "${TABLE_LOC}/data/business_date=2026-07-21"
hdfs dfs -ls "${TABLE_LOC}/metadata" | grep metadata.json | tail -5
```

---

### T1 — Spark 세션 연결 (`test_t1_spark_session_active`)

**의미:** YARN · Kerberos · Spark가 정상인지 확인합니다. 테이블·스토리지 변경 없음.

**Spark SQL**

```sql
SELECT current_catalog() AS catalog, current_database() AS db;
SELECT version() AS spark_version;
```

**Storage**

```bash
hdfs dfs -test -d "${TABLE_LOC}" && echo "table location exists"
```

**YARN (참고)**

```bash
yarn application -list | grep -E 'guide-validator|iceberg-maintenance' || true
```

---

### T2-A — 테이블 등록 · Iceberg Provider (`test_t2_show_tables_and_describe`)

**의미:** Metastore에 테이블이 등록됐고, 형식이 Iceberg인지 확인합니다.

**Spark SQL**

```sql
USE spark_catalog;

SHOW TABLES IN iceberg_compaction_test;

DESCRIBE TABLE EXTENDED spark_catalog.iceberg_compaction_test.txn_events;
-- Provider = iceberg 확인
```

**Storage — Location과 실제 디렉터리 일치**

```bash
hdfs dfs -ls "${TABLE_LOC}"
hdfs dfs -ls "${TABLE_LOC}/metadata" | tail -10
```

---

### T2-B — Iceberg 메타데이터 `.files` (`test_t2_iceberg_metadata_files`)

**의미:** Iceberg가 추적하는 **DATA / delete 파일 목록**을 SQL로 조회합니다.

**Spark SQL**

```sql
SELECT file_path, file_size_in_bytes, content, partition
FROM iceberg_compaction_test.txn_events.files
LIMIT 10;

SELECT content, count(*) AS file_cnt
FROM iceberg_compaction_test.txn_events.files
GROUP BY content;
```

**Storage — SQL의 file_path와 disk 대조**

위 쿼리에서 `file_path` 몇 개를 복사한 뒤:

```bash
# file_path 예: hdfs://ns1/user/hive/warehouse/.../xxx.parquet
#           또는 ofs://ozone1784520717/.../xxx.parquet
hdfs dfs -ls "hdfs://ns1/user/hive/warehouse/iceberg_compaction_test.db/txn_events/data/business_date=2026-07-21/"
```

---

### T3 — Orphan 파일 dry-run (`test_t3_remove_orphan_files_dry_run`)

**의미:** 장부(metadata)에 없는 **고아 파일 후보**를 조회만 합니다. **삭제하지 않습니다.**

**Spark SQL**

```sql
CALL spark_catalog.system.remove_orphan_files(
  table => 'iceberg_compaction_test.txn_events',
  older_than => timestamp '2000-01-01 00:00:00',
  dry_run => true
);
```

**Storage**

dry-run 결과에 나온 `file_path`가 disk에 존재하는지 확인:

```bash
hdfs dfs -test -e "hdfs://ns1/path/from/dry_run_result.parquet" && echo "exists on disk"
```

의도적 orphan 테스트: `python scripts/inject_orphan_files.py` 실행 후 dry-run을
다시 호출합니다.

---

### T4 — Manifest 재작성 (`test_t4_rewrite_manifests`)

**의미:** DATA parquet는 그대로 두고 **manifest(색인)만** 정리합니다. planning 개선 목적.

**Spark SQL — 실행 전후 비교**

```sql
-- BEFORE
SELECT count(*) AS manifest_cnt FROM iceberg_compaction_test.txn_events.manifests;
SELECT count(*) AS snapshot_cnt FROM iceberg_compaction_test.txn_events.snapshots;

CALL spark_catalog.system.rewrite_manifests(
  table => 'iceberg_compaction_test.txn_events',
  use_caching => false
);

-- AFTER
SELECT count(*) AS manifest_cnt FROM iceberg_compaction_test.txn_events.manifests;
SELECT count(*) AS snapshot_cnt FROM iceberg_compaction_test.txn_events.snapshots;

SELECT made_current_at, snapshot_id, summary
FROM iceberg_compaction_test.txn_events.history
ORDER BY made_current_at DESC
LIMIT 5;
```

**Storage**

```bash
# metadata/ 아래 avro·json 변화 (data/ parquet 개수는 보통 동일)
hdfs dfs -ls "${TABLE_LOC}/metadata" | grep -E '\.avro|metadata\.json' | tail -10
hdfs dfs -count "${TABLE_LOC}/data"
```

**기대:** snapshot +1, manifest 수 변화 가능, `data/` parquet 개수는 거의 동일.

---

### T5 — Data file compaction (`test_t5_rewrite_data_files_partition`)

**의미:** 한 파티션(`2026-07-21`)의 **작은 parquet를 큰 파일로 합칩니다.** 가이드 §3 핵심.

**Spark SQL — 실행 전후 비교**

```sql
-- BEFORE
SELECT count(*) AS files,
       cast(avg(file_size_in_bytes) AS bigint) AS avg_bytes,
       sum(file_size_in_bytes) AS total_bytes
FROM iceberg_compaction_test.txn_events.files
WHERE content = 'DATA'
  AND partition.business_date = DATE '2026-07-21';

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

-- AFTER
SELECT count(*) AS files,
       cast(avg(file_size_in_bytes) AS bigint) AS avg_bytes,
       sum(file_size_in_bytes) AS total_bytes
FROM iceberg_compaction_test.txn_events.files
WHERE content = 'DATA'
  AND partition.business_date = DATE '2026-07-21';

-- 논리 row 수는 동일해야 함
SELECT count(*) FROM iceberg_compaction_test.txn_events
WHERE business_date = DATE '2026-07-21';
```

**Storage**

```bash
hdfs dfs -count -h "${TABLE_LOC}/data/business_date=2026-07-21"
hdfs dfs -ls -h "${TABLE_LOC}/data/business_date=2026-07-21"
hdfs dfs -du -h "${TABLE_LOC}/data"
hdfs dfs -ls "${TABLE_LOC}/metadata" | grep metadata.json | tail -3
```

| 지표 | seed 직후 (BEFORE) | compaction 후 (AFTER) |
|------|-------------------|----------------------|
| 파티션 DATA file count (`.files`) | ~20 | ~1–5 |
| avg file size | 작음 | 큼 |
| logical rows | ~120k | 동일 |
| snapshots | N | N+1 |

> disk의 parquet **총 개수**는 expire 전까지 old + new가 공존할 수 있습니다.
> **`.files` 메타데이터**가 “현재 snapshot 기준 live 파일”을 보여 줍니다.

---

### T6 — Destructive tier (선택, `CDP_ALLOW_DESTRUCTIVE=true`)

pytest `-m "cdp and destructive"` 또는 운영 runbook 순서로 실행합니다.

#### T6-A — `expire_snapshots`

**Spark SQL**

```sql
SELECT count(*) AS snapshot_cnt FROM iceberg_compaction_test.txn_events.snapshots;

CALL spark_catalog.system.expire_snapshots(
  table => 'iceberg_compaction_test.txn_events',
  older_than => timestamp '2000-01-01 00:00:00',
  retain_last => 20,
  max_concurrent_deletes => 4
);

SELECT count(*) AS snapshot_cnt FROM iceberg_compaction_test.txn_events.snapshots;
```

**Storage** — 만료 후 unreferenced 파일 정리 시 disk 사용량 감소 가능 (지연될 수 있음)

```bash
hdfs dfs -du -h "${TABLE_LOC}"
hdfs dfs -count -h "${TABLE_LOC}/data"
```

#### T6-B — `rewrite_position_delete_files`

**Spark SQL**

```sql
SELECT count(*) FROM iceberg_compaction_test.txn_events.files
WHERE content = 'POSITION_DELETES';

CALL spark_catalog.system.rewrite_position_delete_files(
  table => 'iceberg_compaction_test.txn_events',
  options => map(
    'min-input-files', '2',
    'max-concurrent-file-group-rewrites', '2',
    'max-file-group-size-bytes', '21474836480'
  )
);

SELECT count(*) FROM iceberg_compaction_test.txn_events.files
WHERE content = 'POSITION_DELETES';
```

**Storage**

```bash
hdfs dfs -ls -R "${TABLE_LOC}/data" | grep -E '\.parquet' | tail -20
hdfs dfs -count -h "${TABLE_LOC}/data"
```

---

### tier ↔ 가이드 ↔ 확인 포인트 요약

| Tier | Integration test | 가이드 | Spark SQL로 볼 것 | Storage로 볼 것 |
|------|------------------|--------|-------------------|-----------------|
| Seed | (사전 준비) | §3–§6 전제 | `.files`, `.snapshots` | `data/`, `metadata/` |
| T1 | Spark session | §1 전제 | `current_catalog()` | Location 존재 |
| T2 | DESCRIBE + `.files` | §1 catalog | `Provider=iceberg`, `.files` | Location 구조 |
| T3 | orphan dry-run | §8 | `CALL ... dry_run=true` | 후보 path 존재 |
| T4 | rewrite_manifests | §5 | `.manifests`, `.history` | `metadata/*.avro` |
| T5 | rewrite_data_files | §3 | 파티션 `.files` count/avg | `data/business_date=.../` |
| T6 | expire / position delete | §4, §6 | `.snapshots`, delete files | disk `du` 변화 |

### metrics CSV로 한 번에 비교 (선택)

단계 전후 수치를 CSV로 저장하려면 기존 helper를 사용할 수 있습니다:

```bash
export MAINTENANCE_RUN_ID=demo_$(date +%Y%m%d_%H%M)
./scripts/capture_metrics.sh before_t5
# T5 CALL 실행 ...
./scripts/capture_metrics.sh after_t5
./scripts/compare_metrics.sh metrics/${MAINTENANCE_RUN_ID}/before_t5.csv \
  metrics/${MAINTENANCE_RUN_ID}/after_t5.csv step2_rewrite_data_files
```

생성되는 SQL은 `src/guide_validator/verification_queries.py`의 `build_metrics_sql()`과
동일합니다.

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
