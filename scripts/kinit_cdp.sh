#!/usr/bin/env bash
# Obtain Kerberos ticket for CDP maintenance jobs.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"

if [[ -f "${PROJECT_ROOT}/.env" ]]; then
  # shellcheck disable=SC1091
  source "${SCRIPT_DIR}/load_env.sh"
fi
# shellcheck disable=SC1091
source "${SCRIPT_DIR}/cdp_client_env.sh"

: "${KERBEROS_PRINCIPAL:=systest@QE-INFRA-AD.CLOUDERA.COM}"

if [[ -z "${KERBEROS_KEYTAB:-}" ]]; then
  echo "ERROR: KERBEROS_KEYTAB is not set." >&2
  echo "Create .env from .env.example or export KERBEROS_KEYTAB=/cdep/keytabs/systest.keytab" >&2
  exit 1
fi

if [[ ! -f "${KERBEROS_KEYTAB}" ]]; then
  echo "ERROR: keytab not found: ${KERBEROS_KEYTAB}" >&2
  exit 1
fi

kinit -kt "${KERBEROS_KEYTAB}" "${KERBEROS_PRINCIPAL}"
echo "Kerberos ticket obtained for ${KERBEROS_PRINCIPAL}"
klist
