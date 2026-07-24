# CDP Kerberos + Auto-TLS 환경 Iceberg Maintenance 실행 가이드

**대상 환경:** CDP Private Cloud Base 7.3.1.600+ · Spark 3.5.4 · Iceberg 1.5.2 · Kerberos · Auto-TLS  
**Kerberos Principal (예시):** `systest@QE-INFRA-AD.CLOUDERA.COM`  
**기준 문서:** [SBI Iceberg Compaction & Maintenance Operational Guide](../guide/index.html)

---

## 이 문서의 목적

운영 가이드 §2 **권장 실행 순서**를 CDP **Kerberos + Auto-TLS** 클러스터에서 **어디서, 무엇을, 어떤 순서로** 실행하는지 고객 담당자가 그대로 따라 할 수 있도록 단계별로 설명합니다.

### 한 번의 maintenance run에서의 실행 순서 (핵심)

```
[0] Kerberos·Auto-TLS·Spark 환경 준비
        ↓
[1] 사전 점검 · table lock          ← §2 첫 단계
        ↓
[2] rewrite_data_files              ← §3 (파티션 단위, where 사용)
        ↓
[3] rewrite_position_delete_files   ← §4 (조건부, table scope)
        ↓
[4] rewrite_manifests               ← §5 (조건부, table scope)
        ↓
[5] expire_snapshots                ← §6 (table scope)
```

**별도 일정 (위 체인에 포함하지 않음)**

| 작업 | 가이드 | 실행 시점 |
|------|--------|-----------|
| Metadata JSON 보존 TBLPROPERTIES | §7 | 테이블 최초 설정 또는 정책 변경 시 1회 |
| Orphan file 정리 | §8 | 주 1회 또는 장애 후, dry-run → 승인 → 삭제 |
| write.target-file-size-bytes | §3 | compaction과 함께 또는 write 정책 변경 시 |

---

## 데이터 변화 검증 (전 단계 공통)

각 maintenance 단계는 **실행 전(pre) · 실행 후(post) 메트릭을 수집**하고, **자동 비교**하여 데이터·메타데이터 변화를 확인합니다.

### 수집되는 메트릭 (17종)

| 메트릭 | 의미 | 단위 |
|--------|------|------|
| `logical_row_count_total` | 테이블 전체 논리 row 수 | rows |
| `logical_row_count_partition` | 대상 파티션 row 수 | rows |
| `data_file_count_total` | DATA file 수 (전체) | files |
| `data_file_count_partition` | DATA file 수 (파티션) | files |
| `data_file_bytes_total` | DATA file 크기 합 (전체) | bytes |
| `data_file_bytes_partition` | DATA file 크기 합 (파티션) | bytes |
| `data_file_avg_size_total` | DATA file 평균 크기 (전체) | bytes |
| `data_file_avg_size_partition` | DATA file 평균 크기 (파티션) | bytes |
| `position_delete_file_count` | position delete file 수 | files |
| `position_delete_file_bytes` | position delete file 크기 | bytes |
| `equality_delete_file_count` | equality delete file 수 | files |
| `all_file_count_total` | 전체 tracked file 수 | files |
| `snapshot_count` | snapshot 수 | snapshots |
| `manifest_count` | manifest 수 | manifests |
| `latest_snapshot_id` | 최신 snapshot ID | id |
| `history_entry_count` | history 항목 수 | entries |

추가로 각 capture마다 **`{label}_history.tsv`**, **`{label}_tblproperties.tsv`** 가 함께 저장됩니다.

### 한 maintenance run 디렉터리

```bash
export MAINTENANCE_RUN_ID=$(date -u +%Y%m%d_%H%M%S)
export METRICS_DIR="./metrics/${MAINTENANCE_RUN_ID}"
mkdir -p "${METRICS_DIR}"

# run 전체 시작 baseline
./scripts/capture_metrics.sh step0_baseline
```

모든 snapshot은 `metrics/${MAINTENANCE_RUN_ID}/` 아래 CSV·TSV로 저장됩니다.

### 3가지 실행 패턴

**패턴 A — 단계별 pre/post 수동 캡처**

```bash
./scripts/capture_metrics.sh step2_pre
# ... procedure 실행 ...
./scripts/capture_metrics.sh step2_post
./scripts/compare_metrics.sh \
  metrics/${MAINTENANCE_RUN_ID}/step2_pre.csv \
  metrics/${MAINTENANCE_RUN_ID}/step2_post.csv \
  step2_rewrite_data_files
```

**패턴 B — pre / post / compare 분리**

```bash
./scripts/run_step_with_verify.sh step2_rewrite_data_files pre
# procedure 실행 (또는 아래 패턴 C)
./scripts/run_step_with_verify.sh step2_rewrite_data_files post
```

**패턴 C — procedure + 검증 일괄 (권장)**

```bash
./scripts/run_step_with_verify.sh step2_rewrite_data_files run
# → pre 캡처 → procedure → post 캡처 → compare 자동 실행
```

`compare_metrics` 출력 예:

```
Metric                           Before          After        Delta Expect             Status
----------------------------------------------------------------------------------------------------
logical_row_count_total           1000000         1000000          +0 unchanged          PASS
data_file_count_partition              120              18         -102 decrease_or_equal PASS
data_file_avg_size_partition      64000000       420000000   +356000000 increase_or_equal  PASS
snapshot_count                           45              46          +1 increase            PASS
```

---

## 0. 실행 전 공통 준비 (Kerberos + Auto-TLS)

### 0.1 어디서 실행하는가

| 항목 | 권장 |
|------|------|
| 실행 위치 | CDP **Gateway/Edge node** (Spark/YARN/HDFS 클라이언트 설치됨) |
| 실행 계정 | maintenance 전용 AD/Kerberos 계정 (예: `systest`) |
| 실행 방식 | `spark-sql` 또는 maintenance 전용 Spark Job (YARN client mode) |
| PROD 주의 | 아래 예시의 `databases.table`, 파티션 값, queue 이름을 **실제 값으로 교체** |

### 0.2 Kerberos 티켓 발급

maintenance Job을 제출하는 **동일 호스트·동일 OS 사용자**에서 티켓을 확보합니다.

```bash
# keytab 방식 (장기 Job / 스케줄러 권장)
export KERBEROS_PRINCIPAL="systest@QE-INFRA-AD.CLOUDERA.COM"
export KERBEROS_KEYTAB="/cdep/keytabs/systest.keytab"

kinit -kt "${KERBEROS_KEYTAB}" "${KERBEROS_PRINCIPAL}"

# 확인
klist
# Expected: Default principal: systest@QE-INFRA-AD.CLOUDERA.COM
```

**실패 시 흔한 원인**

| 증상 | 확인 사항 |
|------|-----------|
| `Client not found in Kerberos database` | principal 이름·realm(`QE-INFRA-AD.CLOUDERA.COM`) 오타 |
| `Keytab contains no suitable keys` | keytab이 해당 principal용으로 생성되었는지 |
| Job 중간 실패 | ticket 만료 → `klist`로 Valid starting/expires 확인, 갱신 cron 또는 keytab 재발급 |

### 0.3 Auto-TLS 신뢰 저장소 (Truststore)

Auto-TLS 활성 CDP에서는 HDFS, YARN, Hive Metastore 등이 **TLS 인증서**를 사용합니다. Spark driver/executor가 클러스터 서비스에 연결하려면 **CM이 배포한 truststore**를 JVM이 신뢰해야 합니다.

```bash
# Edge node에서 Cloudera parcel/environment 로드 (경로는 사이트마다 다를 수 있음)
source /var/lib/cloudera-scm-agent/build/7.3.1.600*/spark3/spark3-env.sh 2>/dev/null || true

# Auto-TLS global truststore (일반적인 CDP 경로 — CM UI에서 실제 경로 확인)
export TRUSTSTORE_PATH="/var/lib/cloudera-scm-agent/agent/cert/cm-auto-global_cacerts.jks"
export TRUSTSTORE_PASSWORD="changeit"   # CM Auto-TLS 기본값 — 환경에 맞게 변경

# Java SSL system properties (spark-submit / spark-sql 공통)
export JAVA_TOOL_OPTIONS="\
-Djavax.net.ssl.trustStore=${TRUSTSTORE_PATH} \
-Djavax.net.ssl.trustStorePassword=${TRUSTSTORE_PASSWORD} \
-Djavax.net.ssl.trustStoreType=JKS"
```

> **운영 팁:** Cloudera Manager → **Administration → Security → Certificates** 에서 Auto-TLS truststore 경로와 타입(JKS/PEM)을 확인하십시오. PEM만 있는 환경은 CM 문서의 `global_cacerts.pem` 경로를 사용합니다.

### 0.4 Spark / Iceberg 세션 변수 (교체 필수)

아래 변수를 **셸 프로필 또는 Airflow/Oozie 변수**에 등록합니다.

```bash
# ── 대상 테이블 (예시) ──
export ICEBERG_CATALOG="spark_catalog"
export TARGET_DATABASE="your_database"
export TARGET_TABLE="your_iceberg_table"
export FULL_TABLE="${TARGET_DATABASE}.${TARGET_TABLE}"

# rewrite_data_files 파티션 predicate (테이블 스키마에 맞게 수정)
export PARTITION_FILTER="business_date = DATE '2026-07-21'"

# ── YARN / Spark 리소스 (maintenance 전용 queue 권장) ──
export SPARK_MASTER="yarn"
export SPARK_QUEUE="default"              # 테스트: default. 운영: 전용 maintenance queue (YARN에 생성 후)
# export SPARK_QUEUE="maintenance"
export SPARK_EXECUTOR_MEMORY="8g"
export SPARK_DRIVER_MEMORY="4g"
export SPARK_NUM_EXECUTORS="4"

# ── Kerberos (YARN에 Job 전달) ──
export SPARK_YARN_PRINCIPAL="${KERBEROS_PRINCIPAL}"
export SPARK_YARN_KEYTAB="${KERBEROS_KEYTAB}"
```

### 0.5 spark-sql 실행 래퍼

이후 모든 단계는 **`scripts/spark_sql_maintenance.sh`** 로 동일한 Kerberos·Auto-TLS·Iceberg 설정을 재사용합니다.

```bash
# 프로젝트 루트에서
chmod +x scripts/kinit_cdp.sh scripts/spark_sql_maintenance.sh

./scripts/kinit_cdp.sh
./scripts/spark_sql_maintenance.sh -e "SHOW DATABASES;"
```

`.env` 사용 시:

```bash
cp .env.example .env
# TARGET_DATABASE, TARGET_TABLE 등 실제 값으로 수정

./scripts/kinit_cdp.sh
# interactive shell: source scripts/load_env.sh
```

> `./scripts/load_env.sh` 단독 실행은 subshell — `source scripts/load_env.sh` 또는 `./scripts/kinit_cdp.sh` 사용.

---

## 1. 사전 점검 · table lock (§2, §10)

**목적:** 잘못된 시점에 compaction을 시작하지 않도록, 테이블 상태·권한·동시 작업 여부를 확인하고 maintenance window를 확정합니다.

### 1.1 Kerberos·Ranger·Storage 권한 확인

```bash
./scripts/spark_sql_maintenance.sh -e "
  SHOW DATABASES;
  DESCRIBE EXTENDED ${FULL_TABLE};
"
```

**체크리스트**

- [ ] `klist`에 `systest@QE-INFRA-AD.CLOUDERA.COM` 유효 티켓 존재
- [ ] `DESCRIBE EXTENDED` 성공 (Hive Metastore + HDFS/Ozone read)
- [ ] Ranger/HMS 정책: 대상 테이블 **SELECT + ALTER + WRITE** (procedure는 commit·파일 삭제 포함)
- [ ] Storage: table location에 **read / write / delete** (expire_snapshots, orphan cleanup 시 delete 필수)

### 1.2 테이블 메타데이터 baseline 캡처 (필수)

```bash
./scripts/capture_metrics.sh step1_baseline
```

**확인 파일**

- `metrics/${MAINTENANCE_RUN_ID}/step1_baseline.csv` — 수치 메트릭
- `metrics/${MAINTENANCE_RUN_ID}/step1_baseline_history.tsv` — 최근 commit 이력
- `metrics/${MAINTENANCE_RUN_ID}/step1_baseline_tblproperties.tsv` — format-version, write.* 속성

**기록·확인할 항목**

| 항목 | baseline에서 확인 | 다음 단계 영향 |
|------|-------------------|----------------|
| `logical_row_count_total` | 현재 row 수 | 모든 단계: **변하면 안 됨** |
| `data_file_count_partition` | 파티션 file 수 | §2 compaction 효과 측정 기준 |
| `position_delete_file_count` | > 0 이면 | §3 후보 |
| `snapshot_count` | 현재 snapshot 수 | §5 만료 baseline |
| `manifest_count` | manifest 수 | §4 후보 판단 |

### 1.3 Format version · delete 유형 확인

```bash
./scripts/spark_sql_maintenance.sh -e "
  SHOW TBLPROPERTIES ${FULL_TABLE};
"
```

| 확인 | 다음 단계 영향 |
|------|----------------|
| `format-version = 2` + position delete 파일 존재 | §4 `rewrite_position_delete_files` **후보** |
| equality delete만 사용 | §4 **생략** |
| manifest 수 많고 파티션 pruning 빈번 | §5 `rewrite_manifests` **후보** |

Position delete 존재 여부:

```bash
./scripts/spark_sql_maintenance.sh -e "
  SELECT count(*) AS position_delete_files
  FROM ${FULL_TABLE}.files
  WHERE content = 'POSITION_DELETES';
"
```

### 1.4 Table lock · 동시 작업 차단 (필수)

**파티션 scope (§3 `rewrite_data_files`)**

1. 대상 파티션(`${PARTITION_FILTER}`)에 **ingest / MERGE / DELETE / streaming commit** 없음 확인  
2. 해당 파티션을 읽는 **배치·Impala/Hive 조회** 종료 확인  
3. 운영 표준에 따라 lock 메타데이터(예: Airflow flag, maintenance 테이블) 기록  

**Table scope (§4–§6)**

- position delete / manifest / snapshot 작업은 **테이블 전체**에 영향  
- 별도 **table-level maintenance window** 확보 (§10 항목 4)  
- 위 파티션 compaction **완료 후** 같은 window 또는 다음 window에서 실행  

### 1.5 YARN queue · 리소스 상한

```bash
# spark-sql 래퍼에 queue/memory가 포함됨 — 제출 전 확인
echo "Queue=${SPARK_QUEUE} Executors=${SPARK_NUM_EXECUTORS} Memory=${SPARK_EXECUTOR_MEMORY}"
```

---

## 2. rewrite_data_files (§3) — 파티션 단위 compaction

**목적:** 작은 data file을 bin-pack하여 read 성능과 metadata 부담을 줄입니다.  
**범위:** **파티션 단위** (`where` predicate). 테이블 전체 full rewrite는 정기 기본값으로 사용하지 않습니다.

### 2.0 데이터 변화 검증 (pre → procedure → post)

```bash
./scripts/run_step_with_verify.sh step2_rewrite_data_files run
```

| 메트릭 | 기대 변화 | 설명 |
|--------|-----------|------|
| `logical_row_count_total` | **변화 없음** | compaction은 row 수를 바꾸지 않음 |
| `logical_row_count_partition` | **변화 없음** | 동일 |
| `data_file_count_partition` | **감소 또는 동일** | small file 병합 |
| `data_file_avg_size_partition` | **증가 또는 동일** | 512 MB 목표에 근접 |
| `data_file_bytes_*` | **≈1% 이내** | 압축·padding 차이 허용 |
| `snapshot_count` | **+1** | 단일 commit (`partial-progress.enabled=false`) |
| `latest_snapshot_id` | **증가** | 새 snapshot 생성 |

procedure 결과(`rewritten_data_files_count`, `added_data_files_count`)는 spark-sql stdout에 출력됩니다. `metrics/.../step2_rewrite_data_files.log`도 함께 보관하십시오.

### 2.1 실행 (수동 시)

```bash
./scripts/spark_sql_maintenance.sh <<EOF
CALL ${ICEBERG_CATALOG}.system.rewrite_data_files(
  table => '${FULL_TABLE}',
  strategy => 'binpack',
  where => '${PARTITION_FILTER}',
  options => map(
    'target-file-size-bytes', '536870912',
    'min-input-files', '5',
    'max-concurrent-file-group-rewrites', '2',
    'max-file-group-size-bytes', '21474836480',
    'partial-progress.enabled', 'false'
  )
);
EOF
```

### 2.2 성공 기준

| 확인 | 설명 |
|------|------|
| `compare_metrics` **RESULT: PASSED** | 위 기대 변화와 일치 |
| YARN Application **SUCCEEDED** | RM UI 또는 `yarn application -list` |
| `rewritten_data_files_count` > 0 | 실제 rewrite 발생 (대상 file 없으면 0 — 사전 file 수 확인) |

### 2.3 (선택) 이후 write 정책 — TBLPROPERTIES

compaction만으로 small file 재발을 막지 못합니다. 정책 확定 후 **1회** 설정:

```bash
./scripts/spark_sql_maintenance.sh -e "
ALTER TABLE ${FULL_TABLE} SET TBLPROPERTIES (
  'write.target-file-size-bytes' = '536870912'
);"
./scripts/capture_metrics.sh step2_tblproperties_post
# step2_tblproperties_post_tblproperties.tsv 에 write.target-file-size-bytes 확인
```

### 2.4 다음 파티션이 있으면

`${PARTITION_FILTER}`만 변경하여 **2.1–2.2를 파티션별로 순차 반복**합니다. YARN/Ozone 용량 검증 전 **파티션 간 병렬 실행 금지**.

---

## 3. rewrite_position_delete_files (§4) — 조건부, table scope

**실행 조건 (아래 모두 해당할 때만)**

1. Iceberg **format v2**
2. **position delete** 파일 존재
3. 이번 window에서 **§2 `rewrite_data_files`를 수행함**
4. Impala stats-optimized `count(*)` 정확성 이슈 대응 필요

**미해당 시:** 이 단계 **전체 생략** (불필요한 scan/commit 방지).

### 3.0 데이터 변화 검증

```bash
./scripts/run_step_with_verify.sh step3_rewrite_position_delete_files run
```

| 메트릭 | 기대 변화 | 설명 |
|--------|-----------|------|
| `logical_row_count_total` | **변화 없음** | delete semantics 유지 |
| `position_delete_file_count` | **감소 또는 동일** | minor compaction + dangling delete 제거 |
| `position_delete_file_bytes` | **감소 또는 동일** | |
| `snapshot_count` | **+1** | commit 1회 |
| `data_file_count_total` | **변화 없음** | data file 자체는 rewrite하지 않음 |

procedure 출력: `rewritten_delete_files_count`, `added_delete_files_count`, `rewritten_bytes_count`.

### 3.1 중요 제약

Iceberg 1.5.2에서는 **`where` 인자 없음** → **테이블 전체** 대상.  
테이블 write 및 중요 read window와 **겹치지 않게** 스케줄하십시오.

### 3.2 실행

```bash
./scripts/spark_sql_maintenance.sh <<EOF
CALL ${ICEBERG_CATALOG}.system.rewrite_position_delete_files(
  table => '${FULL_TABLE}',
  options => map(
    'min-input-files', '2',
    'max-concurrent-file-group-rewrites', '2',
    'max-file-group-size-bytes', '21474836480'
  )
);
EOF
```

### 3.3 성공 기준

- `compare_metrics` **RESULT: PASSED**
- `rewritten_delete_files_count` / `added_delete_files_count` 확인
- `step3_*_post.csv`의 `position_delete_file_count` ≤ pre 값

---

## 4. rewrite_manifests (§5) — 조건부, table scope

**실행 조건:** manifest 수가 많고 **파티션 필터 조회가 빈번**하여 planning time이 문제일 때.

**목적:** manifest 파일 정리 → **scan planning** 개선 (metadata JSON 삭제 아님).

### 4.0 데이터 변화 검증

```bash
./scripts/run_step_with_verify.sh step4_rewrite_manifests run
```

| 메트릭 | 기대 변화 | 설명 |
|--------|-----------|------|
| `logical_row_count_total` | **변화 없음** | 데이터 불변 |
| `manifest_count` | **감소 또는 동일** | manifest 병합 |
| `snapshot_count` | **+1** | commit 1회 |
| `data_file_count_total` | **변화 없음** | data file 미변경 |

procedure 출력: `rewritten_manifests_count`, `added_manifests_count`.

### 4.1 실행

파티션 compaction(§2) **완료 후**, 필요 테이블만 **별도 window**에서:

```bash
./scripts/spark_sql_maintenance.sh <<EOF
CALL ${ICEBERG_CATALOG}.system.rewrite_manifests(
  table => '${FULL_TABLE}',
  use_caching => false
);
EOF
```

`use_caching=false`: executor 메모리 압박 완화 (대형 manifest 테이블 권장 시작값).

### 4.2 채택 여부 결정

- `compare_metrics` **PASSED** + planning time 개선 여부
- `step4_*_history.tsv`에서 `replace` 또는 manifest 관련 operation 확인
- 개선 없으면 정기 실행 목록에서 **제외**

---

## 5. expire_snapshots (§6) — table scope

**목적:** 업무 보존 정책에 따라 **오래된 snapshot** 및 더 이상 필요 없는 data/delete 파일 정리.  
**주의:** 만료된 snapshot으로 **time travel / rollback 불가**. 보존 일수·최소 snapshot 수는 **업무·감사 요구**로 확정.

### 5.0 데이터 변화 검증

```bash
./scripts/run_step_with_verify.sh step5_expire_snapshots run
```

| 메트릭 | 기대 변화 | 설명 |
|--------|-----------|------|
| `logical_row_count_total` | **변화 없음** | live snapshot 데이터 유지 |
| `snapshot_count` | **감소 또는 동일** | 오래된 snapshot 제거 |
| `all_file_count_total` | **감소 또는 동일** | 고아 data/delete file 물리 삭제 |
| `data_file_bytes_total` | **감소 또는 동일** | 더 이상 참조되지 않는 file 정리 |
| `latest_snapshot_id` | **report** | 현재 snapshot은 유지 |

procedure 출력: `deleted_data_files_count`, `deleted_position_delete_files_count`, `deleted_manifest_files_count` 등.

**`step5_*_history.tsv`**: 만료 후에도 최소 `retain_last`개 ancestor snapshot이 남아 있는지 확인.

### 5.1 보존 정책 예시 (시작값 — 그대로 PROD 적용 금지)

```bash
./scripts/spark_sql_maintenance.sh <<EOF
CALL ${ICEBERG_CATALOG}.system.expire_snapshots(
  table => '${FULL_TABLE}',
  older_than => TIMESTAMPADD(DAY, -30, CURRENT_TIMESTAMP),
  retain_last => 20,
  max_concurrent_deletes => 4
);
EOF
```

| 파라미터 | 의미 |
|----------|------|
| `older_than` | 이 시각 **이전** snapshot 후보 만료 |
| `retain_last` | 최소 **N개** ancestor snapshot은 `older_than`과 무관하게 유지 |
| `max_concurrent_deletes` | HDFS/Ozone·NN/OM 부하에 맞게 조정 |

### 5.2 성공 기준

- `compare_metrics` **RESULT: PASSED**
- `snapshot_count` 감소폭이 `retain_last`·`older_than` 정책과 일치
- `logical_row_count_total` **불변**

---

## 6. Metadata JSON 보존 (§7) — 별도 1회 설정

`expire_snapshots`만으로는 **이전 metadata JSON** lifecycle이 충분히 관리되지 않습니다.  
아래 **두 속성은 반드시 함께** 설정합니다.

```bash
./scripts/run_step_with_verify.sh step6_metadata_properties run
```

| 검증 | 방법 |
|------|------|
| TBLPROPERTIES 반영 | `step6_metadata_properties_post_tblproperties.tsv`에 두 key 존재 |
| row/data 불변 | `compare_metrics`에서 `logical_row_count_total` unchanged |
| snapshot/file | **변화 없음** (ALTER only) |

수동 실행:

```bash
./scripts/spark_sql_maintenance.sh -e "
ALTER TABLE ${FULL_TABLE} SET TBLPROPERTIES (
  'write.metadata.delete-after-commit.enabled' = 'true',
  'write.metadata.previous-versions-max' = '100'
);"
./scripts/capture_metrics.sh step6_tblproperties_post
```

streaming table은 commit 빈도가 높아 `100`이 짧을 수 있습니다. **테이블별** 산정하십시오.

---

## 7. Orphan file 정리 (§8) — 주간·승인형 (maintenance 체인 외)

**§2 실행 순서에 포함하지 않습니다.** 실패 write·container kill 후 또는 **주 1회** 점검.

### 7.0 데이터 변화 검증

**7a. dry-run (데이터 변화 없음)**

```bash
./scripts/run_step_with_verify.sh step7_orphan_dry_run run
```

| 메트릭 | 기대 변화 |
|--------|-----------|
| `logical_row_count_total` | **변화 없음** |
| `all_file_count_total` | **변화 없음** |
| `data_file_count_total` | **변화 없음** |

dry-run stdout의 `orphan_file_location` 목록을 저장·검토합니다 (`metrics/.../step7_orphan_dry_run.log`).

**7b. 승인 후 실제 삭제**

```bash
./scripts/run_step_with_verify.sh step7_orphan_delete run
```

| 메트릭 | 기대 변화 |
|--------|-----------|
| `logical_row_count_total` | **변화 없음** |
| tracked file 메트릭 | **변화 없음** (orphan은 metadata 미참조 file) |

> orphan 삭제는 `.files` 메트릭에 반영되지 않을 수 있습니다. dry-run 목록과 storage 사용량 변화를 함께 확인하십시오.

### 7.1 1단계 — dry-run (삭제 없음)

```bash
./scripts/spark_sql_maintenance.sh <<EOF
CALL ${ICEBERG_CATALOG}.system.remove_orphan_files(
  table => '${FULL_TABLE}',
  older_than => TIMESTAMPADD(DAY, -7, CURRENT_TIMESTAMP),
  dry_run => true
);
EOF
```

### 7.2 2단계 — 검토 · 승인 · 실제 삭제

운영·스토리지 담당 **명시적 승인 후**:

```bash
./scripts/spark_sql_maintenance.sh <<EOF
CALL ${ICEBERG_CATALOG}.system.remove_orphan_files(
  table => '${FULL_TABLE}',
  older_than => TIMESTAMPADD(DAY, -7, CURRENT_TIMESTAMP)
);
EOF
```

`older_than`은 **가장 긴 write/재시도 시간**보다 길어야 합니다.

---

## 8. 단계별 요약표 (고객용)

| 순서 | Procedure | Scope | 필수/조건부 | 데이터 변화 검증 |
|------|-----------|-------|-------------|------------------|
| 0 | 환경 준비 | — | 필수 | `step0_baseline` |
| 1 | 사전 점검·lock | partition/table | 필수 | `step1_baseline` |
| 2 | rewrite_data_files | **partition** | 필수 | pre/post + compare (file↓ avg↑ snapshot+1) |
| 3 | rewrite_position_delete_files | **table** | 조건부 | pre/post + compare (pos delete↓ snapshot+1) |
| 4 | rewrite_manifests | **table** | 조건부 | pre/post + compare (manifest↓ snapshot+1) |
| 5 | expire_snapshots | **table** | 정책 확정 후 | pre/post + compare (snapshot↓ file↓ row=) |
| — | metadata TBLPROPERTIES | table | 1회 설정 | tblproperties.tsv 확인 |
| — | remove_orphan_files | **table** | 주간·승인 | dry-run: no change / delete: row= |

### 전체 run 예시 (파티션 1개, 조건부 단계 포함)

```bash
export MAINTENANCE_RUN_ID=$(date -u +%Y%m%d_%H%M%S)
./scripts/kinit_cdp.sh

./scripts/capture_metrics.sh step0_baseline
./scripts/capture_metrics.sh step1_baseline

./scripts/run_step_with_verify.sh step2_rewrite_data_files run
./scripts/run_step_with_verify.sh step3_rewrite_position_delete_files run   # 조건 충족 시
./scripts/run_step_with_verify.sh step4_rewrite_manifests run               # 조건 충족 시
./scripts/run_step_with_verify.sh step5_expire_snapshots run

# orphan은 별도 window
./scripts/run_step_with_verify.sh step7_orphan_dry_run run
# 승인 후
./scripts/run_step_with_verify.sh step7_orphan_delete run

# 전체 산출물
ls -la metrics/${MAINTENANCE_RUN_ID}/
```

---

## 9. 장애 대응 (Kerberos · Auto-TLS)

| 오류 메시지 (예) | 원인 | 조치 |
|------------------|------|------|
| `GSS initiate failed` | ticket 없음/만료 | `./scripts/kinit_cdp.sh`, `klist` |
| `javax.net.ssl.SSLHandshakeException` | truststore 미설정 | §0.3 `JAVA_TOOL_OPTIONS`, CM 인증서 경로 |
| `Permission denied: user=...` HDFS/Ozone | Ranger/storage | principal에 RW(D) 권한 |
| `Cannot find catalog plugin` | Iceberg extension 미적용 | `spark.sql.extensions` 확인 |
| `Procedure not found` | catalog名 오류 | `${ICEBERG_CATALOG}.system.*` 확인 |

---

## 10. 검증 프로젝트와의 연계

이 저장소의 자동 검증·CDP 통합 테스트 (Python **3.11** — `python3.11` / `.venv`):

```bash
./scripts/setup_venv.sh          # python3.11 로 venv 생성
source .venv/bin/activate
python --version                 # Python 3.11.x

# 문서 정적 검증
validate-guide --skip-links

# CDP edge node — .env에 Kerberos/Auto-TLS/테스트 테이블 설정 후
pytest tests/integration/ -m "cdp and not destructive" -v
```

Maintenance shell 스크립트(`kinit_cdp.sh`, `run_step_with_verify.sh` 등)는 venv 없이 동작합니다.
Python helper(`capture_metrics.sh` 등)는 `.env`의 `PYTHON=python3.11`을 사용합니다.

> **`python`(2.7)·`python3`(3.8 parcel)은 사용하지 마세요.**

**pip editable 설치 실패 시** (`setup.py not found` / old pip 21.x):

```bash
source .venv/bin/activate
python -m pip install --upgrade pip setuptools wheel
python -m pip install -e ".[dev]"
```

---

*Cloudera Professional Services · SBI CDP Implementation · Kerberos + Auto-TLS Runbook*
