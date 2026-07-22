#!/usr/bin/env bash
# Obtain Kerberos ticket for CDP maintenance jobs.
set -euo pipefail

: "${KERBEROS_PRINCIPAL:=systest@QE-INFRA-AD.CLOUDERA.COM}"

if [[ -z "${KERBEROS_KEYTAB:-}" ]]; then
  echo "ERROR: KERBEROS_KEYTAB is not set." >&2
  echo "Example: export KERBEROS_KEYTAB=/cdep/keytabs/systest.keytab" >&2
  exit 1
fi

if [[ ! -f "${KERBEROS_KEYTAB}" ]]; then
  echo "ERROR: keytab not found: ${KERBEROS_KEYTAB}" >&2
  exit 1
fi

kinit -kt "${KERBEROS_KEYTAB}" "${KERBEROS_PRINCIPAL}"
echo "Kerberos ticket obtained for ${KERBEROS_PRINCIPAL}"
klist
