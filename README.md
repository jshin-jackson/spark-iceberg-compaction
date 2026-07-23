# Iceberg 테이블 정리 가이드 — 쉬운 설명서

> **SBI(SBI 은행)용 Iceberg 유지보수 가이드**가 맞는지, CDP 클러스터에서 실제로
> 돌아가는지 확인하는 프로젝트입니다.  
> CDP Private Cloud Base 7.3.1.600+ · Spark 3.5.4 · Iceberg 1.5.2

**바로 시작:** [5. 기본 가이드 — 처음부터 끝까지](#5-기본-가이드--처음부터-끝까지-권장) (seed → pytest)

---

## 1. 이게 뭔가요?

### 한 줄 요약

**“은행 거래 장부(Iceberg 테이블)를 깔끔하게 정리하는 방법”** 이 적혀 있는
**설명서(HTML 가이드)** 가 맞는지, **연습용 테이블**에서 **자동으로 시험**해 보는
프로젝트입니다.

### 왜 필요한가요?

데이터를 계속 넣으면 파일이 **작은 조각**으로 많이 쌓입니다.  
마치 **책 한 권을 100장짜리 종이 1000장**으로 나눠 보관하는 것과 비슷합니다.

이렇게 되면:

- 찾기가 느려지고
- 정리(유지보수)가 필요해집니다

이 프로젝트는 **정리 방법 설명서**와 **실제 정리 명령**이 맞게 동작하는지
확인합니다.

---

## 2. Iceberg — 아주 쉽게

Iceberg를 **은행 거래 장부**라고 생각해 보세요.

| 말 | 쉬운 뜻 | 컴퓨터 안에서는 |
|----|---------|----------------|
| **테이블** | 거래 장부 한 권 | `iceberg_compaction_test.txn_events` |
| **데이터 파일** | 거래 내역이 적힌 종이 묶음 | HDFS/Ozone의 `.parquet` 파일 |
| **파티션** | 날짜별 서랍 (예: 7월 21일) | `business_date=2026-07-21` 폴더 |
| **스냅샷** | “그때 장부 상태” 사진 | commit 할 때마다 하나씩 생김 |
| **매니페스트** | “어떤 종이가 어느 서랍에 있는지” 목록 | `metadata/` 안의 파일 |
| **정리(compaction)** | 작은 종이 묶음 → 큰 묶음으로 합치기 | `rewrite_data_files` |

### 테이블 폴더는 이렇게 생겼어요

```
{테이블 위치}/
├── metadata/     ← 장부의 “목차·버전 기록” (Iceberg 두뇌)
└── data/
    └── business_date=2026-07-21/
        └── *.parquet   ← 실제 거래 데이터
```

**두 가지로 볼 수 있어요**

- **Spark SQL** → Iceberg가 **지금 쓰는** 파일 목록 (`.files` 등)
- **hdfs 명령** → 디스크에 **실제로 있는** 모든 파일  
  (정리 직후에는 옛날 파일이 잠깐 남을 수도 있어요)

---

## 3. 우리 lab 정보 (기억해 두세요)

| 저장소 | 이름 | 주소 예시 |
|--------|------|-----------|
| HDFS | NameService **`ns1`** | `hdfs://ns1/...` |
| Ozone | Service ID **`ozone1784520717`** | `ofs://ozone1784520717/...` |

**HDFS HA (standby NameNode 경고)**  
Spark/YARN이 `host:8020` standby NameNode에 붙으면 `Operation category READ is not supported in state standby` 가
나올 수 있습니다. `.env`에 `HADOOP_CONF_DIR`, `HDFS_NAMESERVICE=ns1`, `spark.hadoop.fs.defaultFS=hdfs://ns1` 이
설정되어 있고, `source scripts/load_env.sh` 또는 `kinit_cdp.sh` 가 `cdp_client_env.sh` 를 불러옵니다.
Python(seed·pytest)은 `cdp_spark.py` 가 같은 설정을 Spark 세션에 넣습니다.

**연습용 테이블** (`.env` 기본값)

| 항목 | 값 |
|------|-----|
| 카탈로그 | `spark_catalog` |
| 데이터베이스 | `iceberg_compaction_test` |
| 테이블 | `txn_events` |
| 전체 이름 | `iceberg_compaction_test.txn_events` |
| 연습 파티션 | `2026-07-21` (business_date) |

### Python 버전 (CDP edge — 꼭 읽기)

이 lab의 `/usr/bin`에는 Python이 **여러 개** 있습니다. **잘못 쓰면 바로 실패**합니다.

| 명령 | 버전 | 이 프로젝트 |
|------|------|-------------|
| `python` | **2.7.18** | ❌ 쓰지 마세요 |
| `python3` | **3.8.12** (parcel) | ❌ venv·pytest에 쓰지 마세요 |
| **`python3.11`** | **3.11.11** | ✅ **이것만** 사용 |

`.env`에 `PYTHON=python3.11` 이 있습니다. `setup_venv.sh`와 shell helper도 이 값을 씁니다.

```bash
python3.11 --version    # Python 3.11.11 이어야 함
```

가상환경(`.venv`)을 켠 뒤에는 `python`이 3.11을 가리킵니다:

```bash
source .venv/bin/activate
python --version        # Python 3.11.11
```

---

## 4. 프로젝트 폴더 — 뭐가 어디 있나요?

```
spark-iceberg-compaction/
├── guide/              ← 고객용 HTML 설명서 (정리 방법)
├── spec/               ← Iceberg 1.5.2 공식 규칙 (기준)
├── scripts/            ← 실행 도구 (로그인, 데이터 만들기, 정리 실행)
├── src/guide_validator/← 검사·SQL 만드는 Python 코드
├── tests/integration/  ← CDP에서 도는 자동 시험 (T1~T6)
└── docs/               ← Kerberos·운영 runbook (더 자세한 글)
```

| 파일 | 하는 일 |
|------|---------|
| `scripts/kinit_cdp.sh` | Kerberos 로그인 (출입증) |
| `scripts/cdp_client_env.sh` | HDFS HA nameservice·Hadoop conf (load_env/kinit에서 자동) |
| `scripts/seed_iceberg_table.py` | 연습용 “지저분한” 테이블 만들기 |
| `scripts/spark_sql_maintenance.sh` | Spark SQL 실행 (설정 자동) |
| `scripts/run_step_with_verify.sh` | 정리 + 전/후 비교 |
| `tests/integration/test_cdp_procedures.py` | 자동 시험 문제지 |

---

## 5. 기본 가이드 — 처음부터 끝까지 (권장)

**이 프로젝트의 기본 사용법**은 아래 순서입니다.

매번 **같은 “정리 전” 상태**에서 시험·데모를 하려면, **pytest 전에 seed로 테이블을
새로 만드는 것**이 필수입니다.  
**pytest만 실행하면 데이터가 자동으로 생기지 않습니다.**

### 한 번에 실행 (복사용)

```bash
cd ~/spark-iceberg-compaction

# ── 최초 1회 ──
cp .env.example .env
chmod +x scripts/*.sh
./scripts/setup_venv.sh          # python3.11 로 .venv 생성

# ── 매번 (처음부터 다시 할 때) ──
source scripts/load_env.sh
./scripts/kinit_cdp.sh
source .venv/bin/activate        # activate 후 python = 3.11

# ★ 핵심: 테이블 삭제 후 새 데이터 생성 (“정리 전” 상태)
python scripts/seed_iceberg_table.py --recreate
# venv 없이: python3.11 scripts/seed_iceberg_table.py --recreate

# (선택) 고아 파일 시연 — T3 dry-run에서 후보가 보이게
python scripts/inject_orphan_files.py --count 3 --age-days 10

# 자동 시험 (T1~T5)
pytest tests/integration/ -m "cdp and not destructive" -v
```

**6 passed**면 CDP에서 안전한 정리 작업(T1~T5)이 잘 동작한다는 뜻입니다.

### 각 단계가 하는 일

| 순서 | 명령 | 하는 일 |
|------|------|---------|
| 1 | `kinit_cdp.sh` | Kerberos 로그인 (클러스터 출입) |
| 2 | `seed --recreate` | 테이블 **삭제 후** 작은 파일 ~20개 등 **정리가 필요한 상태** 만들기 |
| 3 | `inject_orphan_files` (선택) | orphan dry-run(T3) 데모용 파일 주입 |
| 4 | `pytest` | T1~T5 자동 검증 (**T4·T5는 테이블을 실제로 변경**) |

### seed 직후 기대값 (참고)

| 항목 | 대략 |
|------|------|
| logical rows | ~120,000 |
| snapshots | ~23 |
| DATA files (7/21 파티션) | ~20 |
| position delete files | ~2 |

### 다시 처음부터 하고 싶을 때

pytest를 **한 번 돌린 뒤**에는 T4(manifest)·T5(compaction) 때문에 테이블이 이미
바뀌어 있습니다. **전/후 데모를 다시** 하려면 seed부터 다시 하세요.

```bash
python scripts/seed_iceberg_table.py --recreate
pytest tests/integration/ -m "cdp and not destructive" -v
```

### T6까지 포함 (선택)

`.env`에 `CDP_ALLOW_DESTRUCTIVE=true` 설정 후:

```bash
pytest tests/integration/ -m cdp -v
```

> seed 직후 **당일** expire 효과를 보려면 `.env.example`의 `EXPIRE_OLDER_THAN`,
> `ORPHAN_OLDER_THAN` override를 참고하세요. 가이드 기본값(30일·7일)은 방금 seed한
> snapshot/orphan에는 거의 적용되지 않습니다.

### pytest만으로 안 되는 것

| 내용 | 방법 |
|------|------|
| 데이터·“정리 전” 상태 만들기 | `seed --recreate` (**기본 가이드 필수**) |
| orphan **실제 삭제** | `run_step_with_verify.sh step7_orphan_delete` |
| metadata TBLPROPERTIES | `run_step_with_verify.sh step6_metadata_properties` |
| 전/후 지표 CSV 비교 | `capture_metrics.sh` + `compare_metrics.sh` |

운영 runbook 전체: [docs/CDP_Kerberos_AutoTLS_Maintenance_Runbook.md](docs/CDP_Kerberos_AutoTLS_Maintenance_Runbook.md)

---

## 6. 처음 설정 (최초 1회)

### 6-1. 설정 파일 만들기

```bash
cd ~/spark-iceberg-compaction
cp .env.example .env
# 필요하면 .env 내용 수정
```

### 6-2. 로그인 (Kerberos)

```bash
chmod +x scripts/*.sh
./scripts/kinit_cdp.sh
```

### 6-3. Python 3.11 가상환경

CDP edge에서는 **`python3.11`** 로 venv를 만듭니다. `python`(2.7)·`python3`(3.8)은
**사용하지 않습니다.**

```bash
# 권장: .env 의 PYTHON=python3.11 사용
./scripts/setup_venv.sh

# 수동
python3.11 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip setuptools wheel
python -m pip install -e ".[dev]"
python --version    # Python 3.11.11 확인
```

> `kinit_cdp.sh` — venv **없이** 동작 (Kerberos만).  
> `spark_sql_maintenance.sh` — CDP `spark-sql` 없으면 **PySpark fallback** (venv 권장).  
> `seed`, `pytest`, `validate-guide` — venv **켠 뒤** `python` 사용 (3.11).  
> venv 없이 Python만 쓸 때는 **`python3.11`** 을 직접 지정하세요.

### 6-4. seed 상세

**[5. 기본 가이드](#5-기본-가이드--처음부터-끝까지-권장)** 의 `seed --recreate` 와 동일합니다.
시험·데모 전에는 **항상** 이 단계부터 시작하세요.

```bash
python scripts/seed_iceberg_table.py --recreate
# 옵션: --batches 30 --rows-per-batch 20000
```

끝나면 터미널에 snapshots·files 개수 **요약**이 출력됩니다.

---

## 7. 자동 시험 (pytest) — T1부터 T6까지

> **먼저 [5. 기본 가이드](#5-기본-가이드--처음부터-끝까지-권장)** 의 `seed --recreate` 를
> 실행한 뒤 pytest를 돌리세요. pytest는 데이터를 만들지 않습니다.

### 시험 돌리기

```bash
source .venv/bin/activate

# 안전한 시험만 (T1~T5)
pytest tests/integration/ -m "cdp and not destructive" -v

# 위험한 시험까지 (T6) — .env에 CDP_ALLOW_DESTRUCTIVE=true 필요
pytest tests/integration/ -m cdp -v
```

### 각 시험이 뭘 확인하나요?

| 시험 | 이름 | 쉬운 설명 | 위험도 |
|------|------|-----------|--------|
| **T1** | Spark 연결 | 컴퓨터(Spark)가 켜졌나? | 안전 |
| **T2** | 테이블 확인 | 장부가 Iceberg 맞나? 파일 목록 보기 | 안전 |
| **T3** | 고아 파일 조회 | 버려진 파일 **목록만** (삭제 안 함) | 안전 |
| **T4** | manifest 정리 | **목차만** 정리 (종이 내용은 그대로) | 보통 |
| **T5** | data file 정리 | **7/21 서랍** 작은 파일 합치기 | 보통 |
| **T6** | snapshot·delete 정리 | 옛 사진 지우기, delete 정리 | **주의** |

### 시험 코드는 어디?

- 준비: `tests/integration/conftest.py` (Spark 연결, `.env` 읽기)
- 문제: `tests/integration/test_cdp_procedures.py`
- SQL 만들기: `src/guide_validator/template_renderer.py`

---

## 8. Spark SQL 사용하기

이 lab에서는 **`spark-sql` 명령을 직접 치지 않습니다.**  
Kerberos·Auto-TLS·Iceberg catalog·HDFS HA 설정이 들어 있는 래퍼 스크립트를 씁니다.

| 구분 | 사용하는 것 | 쓰지 않는 것 |
|------|-------------|--------------|
| SQL 실행 | `./scripts/spark_sql_maintenance.sh` | `spark-sql`, `spark3-sql` 직접 실행 |
| PySpark lab | venv 켠 뒤 래퍼 실행 (자동 fallback) | `.venv/bin/spark-sql` (PySpark shim) |
| 데이터 적재 | `python scripts/seed_iceberg_table.py` | Spark SQL로 INSERT |

CDP `spark-sql` CLI가 없으면 stderr에  
`NOTE: using PySpark SQL runner (same settings as seed/pytest).` 가 나옵니다. **정상**입니다.

---

### 8-1. 진입 전 준비 (매번)

```bash
cd ~/spark-iceberg-compaction

# 1) .env 변수 로드 (Kerberos, Iceberg catalog, HDFS HA 등)
source scripts/load_env.sh

# 2) Kerberos 티켓
./scripts/kinit_cdp.sh

# 3) venv (PySpark fallback lab에서는 권장)
source .venv/bin/activate

# 4) (선택) seed 직후 “정리 전” 상태에서 SQL 확인할 때
python scripts/seed_iceberg_table.py --recreate
```

연습 테이블 기본값 (`.env`):

| 항목 | 값 |
|------|-----|
| 카탈로그 | `spark_catalog` |
| 테이블 | `iceberg_compaction_test.txn_events` |
| 파티션 | `business_date = 2026-07-21` |

---

### 8-2. SQL 실행 방법 3가지

모든 방법이 **같은 스크립트**를 씁니다. YARN client mode로 job이 제출되며,  
SELECT는 결과 표가 터미널에 출력되고, CALL은 procedure 결과가 출력됩니다.

#### (1) 한 줄 실행 — `-e` (가장 많이 씀)

```bash
./scripts/spark_sql_maintenance.sh -e "SELECT 1;"
```

```bash
./scripts/spark_sql_maintenance.sh -e "SELECT current_catalog(), version();"
```

```bash
./scripts/spark_sql_maintenance.sh -e "
USE spark_catalog;
SELECT count(*) FROM iceberg_compaction_test.txn_events;
"
```

> `-e` 뒤 문자열 전체가 **SQL 한 덩어리**입니다. 따옴표 안에서 `;` 로 여러 문장을
> 이어 붙일 수 있습니다.

#### (2) SQL 파일 실행 — `-f`

```bash
cat > /tmp/check_files.sql <<'SQL'
USE spark_catalog;

SELECT content, count(*)
FROM iceberg_compaction_test.txn_events.files
GROUP BY content;
SQL

./scripts/spark_sql_maintenance.sh -f /tmp/check_files.sql
```

#### (3) heredoc (여러 줄 · CALL procedure에 적합)

```bash
./scripts/spark_sql_maintenance.sh <<'SQL'
USE spark_catalog;

CALL spark_catalog.system.rewrite_manifests(
  table => 'iceberg_compaction_test.txn_events',
  use_caching => false
);
SQL
```

> heredoc 끝 `SQL` 은 **줄 맨 앞**에만 써야 합니다 (앞에 공백 없음).

#### (4) 대화형 REPL — 이 lab에서는 보통 불가

인자 없이 `./scripts/spark_sql_maintenance.sh` 를 실행하면 CDP `spark-sql` REPL에
들어갑니다. 이 lab은 PySpark fallback이라 **REPL 대신 `-e` / `-f` / heredoc** 을
사용하세요.

PySpark만 쓰려면 `.env`에 `SPARK_SQL_BACKEND=pyspark` 를 넣을 수 있습니다.

---

### 8-3. 정리 procedure — shell 한 줄로 (자동)

가이드 단계별 CALL을 **전/후 지표와 함께** 돌리려면:

```bash
source scripts/load_env.sh
./scripts/kinit_cdp.sh
source .venv/bin/activate

# 예: T5 data file compaction (step2)
./scripts/run_step_with_verify.sh step2_rewrite_data_files run
```

| step id | 하는 일 (가이드) |
|---------|------------------|
| `step2_rewrite_data_files` | T5 — 작은 data file 합치기 |
| `step3_rewrite_position_delete_files` | delete file 정리 |
| `step4_rewrite_manifests` | T4 — manifest 정리 |
| `step5_expire_snapshots` | snapshot 만료 |
| `step6_metadata_properties` | metadata TBLPROPERTIES |
| `step7_orphan_dry_run` | T3 — orphan 목록만 (dry-run) |
| `step7_orphan_delete` | orphan 실제 삭제 (**주의**) |

모드: `pre` (실행 전 지표만) · `post` (실행 후) · `run` (pre → procedure → post → 비교)

---

### 8-4. 단계별 SQL — 무엇을 치면 되나?

아래 SQL은 **[8-2](#8-2-sql-실행-방법-3가지)** 의 `-e` / heredoc / `-f` 중 아무 방식으로
실행하면 됩니다. 예시는 `-e` 한 줄 형태로 적습니다.

#### 0단계 — 테이블 Location 확인

```bash
./scripts/spark_sql_maintenance.sh -e "
USE spark_catalog;
DESCRIBE TABLE EXTENDED spark_catalog.iceberg_compaction_test.txn_events;
"
```

`Location` 행의 주소를 복사한 뒤 HDFS 확인:

```bash
export TABLE_LOC="hdfs://ns1/user/hive/warehouse/iceberg_compaction_test.db/txn_events"
hdfs dfs -ls "${TABLE_LOC}/data/business_date=2026-07-21"
```

#### Seed 직후 — “지저분한 상태” 확인

```bash
./scripts/spark_sql_maintenance.sh -e "
USE spark_catalog;
SELECT count(*) FROM iceberg_compaction_test.txn_events;
SELECT content, count(*) FROM iceberg_compaction_test.txn_events.files GROUP BY content;
SELECT count(*) FROM iceberg_compaction_test.txn_events.snapshots;
"
```

기대: rows ~120,000 · DATA files ~20 · snapshots ~23

#### T1 — Spark 연결

```bash
./scripts/spark_sql_maintenance.sh -e "SELECT current_catalog(), version();"
```

#### T2 — Iceberg 테이블·파일 목록

```bash
./scripts/spark_sql_maintenance.sh -e "
USE spark_catalog;
DESCRIBE TABLE EXTENDED spark_catalog.iceberg_compaction_test.txn_events;
SELECT file_path, file_size_in_bytes, content
FROM iceberg_compaction_test.txn_events.files LIMIT 5;
"
```

`Provider = iceberg` 인지 확인.

#### T3 — orphan 후보 (삭제 안 함)

```bash
./scripts/spark_sql_maintenance.sh <<'SQL'
CALL spark_catalog.system.remove_orphan_files(
  table => 'iceberg_compaction_test.txn_events',
  older_than => timestamp '2000-01-01 00:00:00',
  dry_run => true
);
SQL
```

#### T4 — manifest 정리

**전:**

```bash
./scripts/spark_sql_maintenance.sh -e "
SELECT count(*) FROM iceberg_compaction_test.txn_events.manifests;
"
```

**실행:**

```bash
./scripts/spark_sql_maintenance.sh <<'SQL'
CALL spark_catalog.system.rewrite_manifests(
  table => 'iceberg_compaction_test.txn_events',
  use_caching => false
);
SQL
```

**후:**

```bash
./scripts/spark_sql_maintenance.sh -e "
SELECT count(*) FROM iceberg_compaction_test.txn_events.manifests;
SELECT snapshot_id, made_current_at
FROM iceberg_compaction_test.txn_events.history
ORDER BY made_current_at DESC LIMIT 3;
"
```

#### T5 — 작은 파일 합치기 (가장 중요)

**전:**

```bash
./scripts/spark_sql_maintenance.sh -e "
SELECT count(*) AS files,
       cast(avg(file_size_in_bytes) AS bigint) AS avg_bytes
FROM iceberg_compaction_test.txn_events.files
WHERE content = 'DATA'
  AND partition.business_date = DATE '2026-07-21';
"
```

**실행** (CDP에서 `where` 는 `make_date` 형식):

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

**후:**

```bash
./scripts/spark_sql_maintenance.sh -e "
SELECT count(*) AS files,
       cast(avg(file_size_in_bytes) AS bigint) AS avg_bytes
FROM iceberg_compaction_test.txn_events.files
WHERE content = 'DATA'
  AND partition.business_date = DATE '2026-07-21';
SELECT count(*) FROM iceberg_compaction_test.txn_events
WHERE business_date = DATE '2026-07-21';
"
```

| | 정리 전 | 정리 후 |
|--|---------|---------|
| 파일 개수 | ~20 | ~1~5 |
| 거래 건수 | ~12만 | **같음** |

#### T6 — (선택) snapshot·delete 정리

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

> PROD 또는 공유 lab에서는 T6 전에 승인·백업·`CDP_ALLOW_DESTRUCTIVE=true` 를 확인하세요.

---

### 8-5. HDFS로 디스크 확인 (Spark SQL과 짝)

Spark SQL은 **Iceberg가 지금 쓰는 파일**을, `hdfs dfs`는 **디스크 전체**를 봅니다.

```bash
export TABLE_LOC="hdfs://ns1/user/hive/warehouse/iceberg_compaction_test.db/txn_events"

hdfs dfs -ls "${TABLE_LOC}/metadata"
hdfs dfs -count -h "${TABLE_LOC}/data/business_date=2026-07-21"
hdfs dfs -ls -h "${TABLE_LOC}/data/business_date=2026-07-21"
```

Ozone 테이블이면 Location이 `ofs://ozone1784520717/...` 일 수 있습니다:

```bash
export TABLE_LOC="ofs://ozone1784520717/volume/bucket/path/txn_events"
hdfs dfs -ls "${TABLE_LOC}/data"
```

---

### 8-6. 자주 나는 메시지

| 메시지 | 의미 |
|--------|------|
| `NOTE: using PySpark SQL runner` | CDP CLI 대신 PySpark 사용 — **정상** |
| `Picked up JAVA_TOOL_OPTIONS` | Auto-TLS truststore — **정상** |
| YARN Application ID 로그 | client mode job 제출 — **정상** |
| `make_date(2026, 7, 21)` | CDP `CALL` where 절용 날짜 형식 |

---

## 9. 직접 눈으로 확인하기 (요약표)

> **상세 CLI·SQL은 [8. Spark SQL 사용하기](#8-spark-sql-사용하기)** 를 보세요.  
> 아래는 **[5. 기본 가이드](#5-기본-가이드--처음부터-끝까지-권장)** 의 `seed --recreate` 직후,
> pytest **전** “정리 전” 상태를 빠르게 훑을 때 쓰는 **요약**입니다.

### 공통 준비

```bash
cd ~/spark-iceberg-compaction
source scripts/load_env.sh
./scripts/kinit_cdp.sh
source .venv/bin/activate
./scripts/spark_sql_maintenance.sh -e "SELECT 1;"
```

---

### 0단계 — 테이블이 디스크 어디에 있나?

**Spark SQL**

```sql
USE spark_catalog;

DESCRIBE TABLE EXTENDED spark_catalog.iceberg_compaction_test.txn_events;
-- Location 행에 적힌 주소가 테이블 폴더입니다
```

**HDFS 예시** (Location이 `hdfs://ns1/...` 일 때)

```bash
export TABLE_LOC="hdfs://ns1/user/hive/warehouse/iceberg_compaction_test.db/txn_events"

hdfs dfs -ls "${TABLE_LOC}"
hdfs dfs -ls "${TABLE_LOC}/metadata"
hdfs dfs -ls "${TABLE_LOC}/data"
hdfs dfs -ls "${TABLE_LOC}/data/business_date=2026-07-21"
```

**Ozone 예시** (Location이 `ofs://ozone1784520717/...` 일 때)

```bash
export TABLE_LOC="ofs://ozone1784520717/volume/bucket/path/txn_events"

hdfs dfs -ls "${TABLE_LOC}"
hdfs dfs -ls "${TABLE_LOC}/metadata"
hdfs dfs -ls "${TABLE_LOC}/data"
```

> Ozone도 `hdfs dfs -ls ofs://ozone1784520717/...` 처럼 쓸 수 있는 경우가 많습니다.

---

### Seed 직후 — “지저분한 상태” 맞나?

**Spark SQL**

```sql
USE spark_catalog;

-- 거래 건수
SELECT count(*) FROM iceberg_compaction_test.txn_events;

-- 파일 종류별 개수 (DATA ~20, delete ~2 정도)
SELECT content, count(*) 
FROM iceberg_compaction_test.txn_events.files 
GROUP BY content;

SELECT count(*) FROM iceberg_compaction_test.txn_events.snapshots;
```

**디스크**

```bash
hdfs dfs -count -h "${TABLE_LOC}/data/business_date=2026-07-21"
hdfs dfs -ls -h "${TABLE_LOC}/data/business_date=2026-07-21"
```

---

### T1 — Spark 잘 붙었나?

**Spark SQL**

```sql
SELECT current_catalog(), version();
```

**디스크**

```bash
hdfs dfs -test -d "${TABLE_LOC}" && echo "테이블 폴더 있음"
```

---

### T2 — Iceberg 테이블 맞나?

**Spark SQL**

```sql
USE spark_catalog;
DESCRIBE TABLE EXTENDED spark_catalog.iceberg_compaction_test.txn_events;
-- Provider = iceberg 인지 확인

SELECT file_path, file_size_in_bytes, content
FROM iceberg_compaction_test.txn_events.files
LIMIT 5;
```

**디스크**

```bash
hdfs dfs -ls "${TABLE_LOC}/metadata" | tail -5
hdfs dfs -ls "hdfs://ns1/user/hive/warehouse/iceberg_compaction_test.db/txn_events/data/business_date=2026-07-21/"
```

---

### T3 — 버려진 파일 후보 (삭제 안 함)

**Spark SQL**

```sql
CALL spark_catalog.system.remove_orphan_files(
  table => 'iceberg_compaction_test.txn_events',
  older_than => timestamp '2000-01-01 00:00:00',
  dry_run => true
);
```

결과에 나온 경로가 disk에 있는지:

```bash
hdfs dfs -test -e "hdfs://ns1/...(결과에 나온 경로)" && echo "있음"
```

---

### T4 — 목차(manifest)만 정리

**실행 전**

```sql
SELECT count(*) FROM iceberg_compaction_test.txn_events.manifests;
```

**실행**

```sql
CALL spark_catalog.system.rewrite_manifests(
  table => 'iceberg_compaction_test.txn_events',
  use_caching => false
);
```

**실행 후**

```sql
SELECT count(*) FROM iceberg_compaction_test.txn_events.manifests;
SELECT snapshot_id, made_current_at 
FROM iceberg_compaction_test.txn_events.history 
ORDER BY made_current_at DESC LIMIT 3;
```

**디스크** — `metadata/` 안 파일 변화, `data/` parquet 개수는 거의 같음

```bash
hdfs dfs -ls "${TABLE_LOC}/metadata" | tail -10
hdfs dfs -count "${TABLE_LOC}/data"
```

---

### T5 — 작은 파일 합치기 (가장 중요)

**실행 전** — 7/21 파티션 파일이 많고 작음 (~20개)

```sql
SELECT count(*) AS files,
       cast(avg(file_size_in_bytes) AS bigint) AS avg_bytes
FROM iceberg_compaction_test.txn_events.files
WHERE content = 'DATA'
  AND partition.business_date = DATE '2026-07-21';
```

**실행**

```sql
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
```

**실행 후** — 파일 수 ↓, 평균 크기 ↑, **거래 건수는 같음**

```sql
SELECT count(*) AS files,
       cast(avg(file_size_in_bytes) AS bigint) AS avg_bytes
FROM iceberg_compaction_test.txn_events.files
WHERE content = 'DATA'
  AND partition.business_date = DATE '2026-07-21';

SELECT count(*) FROM iceberg_compaction_test.txn_events
WHERE business_date = DATE '2026-07-21';
```

| | 정리 전 | 정리 후 |
|--|---------|---------|
| 파일 개수 | ~20 | ~1~5 |
| 파일 크기 | 작음 | 큼 |
| 거래 건수 | ~12만 | **같음** |

**디스크**

```bash
hdfs dfs -count -h "${TABLE_LOC}/data/business_date=2026-07-21"
hdfs dfs -ls -h "${TABLE_LOC}/data/business_date=2026-07-21"
```

---

### T6 — (선택) 더 강한 정리

`.env`에 `CDP_ALLOW_DESTRUCTIVE=true` 후:

```bash
pytest tests/integration/ -m "cdp and destructive" -v
```

**expire_snapshots** — 옛 snapshot 지우기

```sql
CALL spark_catalog.system.expire_snapshots(
  table => 'iceberg_compaction_test.txn_events',
  older_than => timestamp '2000-01-01 00:00:00',
  retain_last => 20,
  max_concurrent_deletes => 4
);
```

**rewrite_position_delete_files** — delete 파일 정리

```sql
CALL spark_catalog.system.rewrite_position_delete_files(
  table => 'iceberg_compaction_test.txn_events',
  options => map(
    'min-input-files', '2',
    'max-concurrent-file-group-rewrites', '2',
    'max-file-group-size-bytes', '21474836480'
  )
);
```

---

## 10. 설명서만 검사하기 (클러스터 없이)

HTML 가이드 문법·링크가 맞는지 **오프라인**으로 확인:

```bash
validate-guide --skip-links
pytest tests/ -m "not cdp and not network" -v
```

---

## 11. 운영할 때 — 더 자세한 글

Kerberos + Auto-TLS 환경에서 **한 단계씩** 정리하고 전/후를 비교하려면:

- [docs/CDP_Kerberos_AutoTLS_Maintenance_Runbook.md](docs/CDP_Kerberos_AutoTLS_Maintenance_Runbook.md)
- [docs/CDP_Kerberos_Keytab_Guide.md](docs/CDP_Kerberos_Keytab_Guide.md)

한 단계 실행 예:

```bash
./scripts/run_step_with_verify.sh step2_rewrite_data_files run
```

전/후 숫자를 CSV로 저장:

```bash
export MAINTENANCE_RUN_ID=demo_$(date +%Y%m%d_%H%M)
./scripts/capture_metrics.sh before_t5
# T5 실행 ...
./scripts/capture_metrics.sh after_t5
```

---

## 12. 정리 순서 (가이드와 같음)

```
사전 점검
  → 작은 파일 합치기 (rewrite_data_files)     ← T5, §3
  → delete 파일 정리 (조건부)                  ← T6, §4
  → manifest 정리 (조건부)                    ← T4, §5
  → snapshot 만료                               ← T6, §6
  → 고아 파일 (별도, dry-run 먼저)              ← T3, §8
```

---

## 13. 자주 묻는 질문

**Q. seed 할 때 `standby` / `8020` / `READ is not supported` 경고가 나와요.**  
A. HDFS HA 환경에서 클라이언트가 **standby NameNode**에 붙었을 때 나는 메시지입니다.
`.env`에 `HADOOP_CONF_DIR=/etc/hadoop/conf`, `HDFS_NAMESERVICE=ns1`,
`SPARK_CONF_spark_hadoop_fs_defaultFS=hdfs://ns1` 이 있는지 확인하고 `source scripts/load_env.sh` 후
다시 seed 하세요. `Picked up JAVA_TOOL_OPTIONS` 는 Auto-TLS용으로 **정상**입니다.

**Q. `spark_sql_maintenance.sh`에서 `SparkSQLCLIDriver` / `spark-sql not found` 에러가 나와요.**  
A. 이 lab처럼 CDP `spark-sql` CLI가 없거나 `CDH/lib/spark3`만 있는 경우, 스크립트가
**PySpark fallback**(`spark_sql_maintenance.py`, seed와 동일 설정)으로 자동 전환합니다.
`NOTE: using PySpark SQL runner` 가 stderr에 나오면 정상입니다.  
CLI를 강제하려면 `.env`에 `SPARK_HOME=...` 지정, PySpark만 쓰려면 `SPARK_SQL_BACKEND=pyspark`.

**Q. `python` / `python3` 쓰면 안 되나요?**  
A. 이 lab에서 `python`은 **2.7**, `python3`는 **3.8** 입니다. 이 프로젝트는
**`python3.11`(3.11.11)** + `.venv` 기준입니다. `.env`의 `PYTHON=python3.11`을
지키세요.

**Q. 테스트만 돌리면 데이터가 새로 생기나요?**  
A. **아니요.** `python3.11 scripts/seed_iceberg_table.py --recreate` (또는 venv 안에서
`python scripts/seed_iceberg_table.py --recreate`) 가 “처음부터”의 **기본**입니다.
[5. 기본 가이드](#5-기본-가이드--처음부터-끝까지-권장) 순서를 따르세요.

**Q. pytest 6개 passed면 PROD에 바로 적용해도 되나요?**  
A. **연습 테이블에서 검증 완료**라는 뜻입니다. PROD는 승인, 권한(Ranger), YARN queue,
보존 기간을 따로 확인해야 합니다.

**Q. Spark SQL과 hdfs ls 결과가 다른데요?**  
A. 정상일 수 있습니다. SQL은 **지금 snapshot이 쓰는 파일**, hdfs는 **disk 전체**를
봅니다. 정리 직후 옛 파일이 남을 수 있습니다.

**Q. `make_date(2026, 7, 21)` 은 왜 쓰나요?**  
A. CDP에서 `CALL` 명령의 날짜 따옴표가 깨지는 경우가 있어서, 따옴표 없이 쓰는
형식입니다.

**Q. 가이드 HTML을 바꿨어요.**  
A. `guide/SBI_Iceberg_Compaction_Maintenance_Guide_reviewed.html` 교체 후
`validate-guide --skip-links` 실행.

---

## 14. 라이선스

Cloudera Professional Services — SBI CDP engagement 내부 도구.
