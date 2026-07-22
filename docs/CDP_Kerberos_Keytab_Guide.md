# CDP Kerberos Keytab 가이드

**Principal:** `systest@QE-INFRA-AD.CLOUDERA.COM`  
**Keytab (CDP edge node):** `/cdep/keytabs/systest.keytab`  
**용도:** Iceberg maintenance Spark Job (YARN client mode)

---

## 1. keytab 배치 (현재 환경)

```bash
ls -l /cdep/keytabs/systest.keytab
# 권장: -r-------- 1 systest cloudera ... systest.keytab

klist -ket /cdep/keytabs/systest.keytab
# Principal: systest@QE-INFRA-AD.CLOUDERA.COM
```

`.env` 설정:

```bash
KERBEROS_PRINCIPAL=systest@QE-INFRA-AD.CLOUDERA.COM
KERBEROS_KEYTAB=/cdep/keytabs/systest.keytab
SPARK_YARN_PRINCIPAL=systest@QE-INFRA-AD.CLOUDERA.COM
SPARK_YARN_KEYTAB=/cdep/keytabs/systest.keytab
```

검증:

```bash
cd ~/spark-iceberg-compaction
cp .env.example .env   # 실제 DB/테이블명으로 수정

./scripts/kinit_cdp.sh
# 또는 interactive shell: source scripts/load_env.sh && echo "$KERBEROS_KEYTAB"
klist
```

> **`source .env` 사용 금지.** `./scripts/kinit_cdp.sh`(자동 .env 로드) 또는 `source scripts/load_env.sh` 사용.  
> `./scripts/load_env.sh` 단독 실행은 subshell이라 export가 부모 shell에 남지 않습니다.

---

## 2. keytab 생성 (Active Directory — 최초 발급 시)

AD 관리자가 Domain Controller에서 실행 (Windows PowerShell):

```powershell
ktpass -princ systest@QE-INFRA-AD.CLOUDERA.COM `
  -mapuser QE-INFRA-AD\systest `
  -pass * `
  -crypto AES256-SHA1 `
  -ptype KRB5_NT_PRINCIPAL `
  -out C:\temp\systest.keytab
```

CDP edge node로 복사:

```bash
sudo mkdir -p /cdep/keytabs
sudo cp systest.keytab /cdep/keytabs/systest.keytab
sudo chown systest:cloudera /cdep/keytabs/systest.keytab
sudo chmod 400 /cdep/keytabs/systest.keytab
```

### 암호화 타입

CDP 클러스터와 일치해야 합니다. `AES256-SHA1` 실패 시 `AES128-SHA1` keytab 추가 생성 후 병합하거나 AD 관리자에게 enctype 맞춤 발급을 요청하십시오.

---

## 3. 흔한 오류

| 메시지 | 조치 |
|--------|------|
| `Keytab contains no suitable keys` | enctype 불일치 → keytab 재생성 |
| `Client not found in Kerberos database` | principal/realm 확인 |
| `ERROR: keytab not found` | `/cdep/keytabs/systest.keytab` 경로·권한 확인 |
| `GSS initiate failed` (Job 중) | ticket 만료 → `kinit -kt` 재실행 또는 cron |

---

## 4. 보안

- keytab을 Git·이메일·공유 드라이브에 업로드하지 않습니다
- 파일 권한 `400`, maintenance 전용 OS 사용자만 read
- 유출 시 AD 비밀번호 reset + keytab 재발급

---

*See also: [CDP_Kerberos_AutoTLS_Maintenance_Runbook.md](CDP_Kerberos_AutoTLS_Maintenance_Runbook.md)*
