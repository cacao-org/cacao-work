#!/usr/bin/env bash
# SPDX-FileCopyrightText: 2026 Olivier Guyon et al
# SPDX-License-Identifier: LGPL-3.0-or-later
#
# Build and optionally deploy an AO simulation report directory to Firebase Hosting.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=../env.sh
source "${SCRIPT_DIR}/../env.sh"

REPORT_DIR="${CACAO_WORK_ROOT}/_work/ao3k_scexao"
SITE_DIR="${CACAO_WORK_ROOT}/_work/_web_site"
SLUG=""
PROJECT_TARGET="${FIREBASE_PROJECT:-}"
HOSTING_SITE_ID=""
INCLUDE_FITS=0
BUILD_ONLY=0
POSITIONAL=()

usage() {
    cat <<'EOF'
Usage: publish-ao-report.sh [OPTIONS] [REPORT_DIR]

Build static HTML pages from an AO simulation report directory (REPORT.md and
optional COMPUTE_REPORT.md + PNG/JSON/CSV assets) and publish to Firebase Hosting.

Options:
  --slug <slug>           Subpath under public/<slug>/ (default: basename of REPORT_DIR)
  --site-dir <dir>        Firebase Hosting staging root (default: _work/_web_site)
  --project <id_or_name>  Target GCP/Firebase project (or set FIREBASE_PROJECT)
  --hosting-site <id>     Explicit Firebase Hosting site ID (default: auto-detect/create)
  --include-fits          Stage large .fits cubes in addition to plots and telemetry
  --build-only            Stage HTML & firebase.json locally without calling Firebase CLI
  -h, --help              Show this help message
EOF
}

while [[ $# -gt 0 ]]; do
    case "$1" in
        --slug)
            SLUG="$2"
            shift 2
            ;;
        --site-dir)
            SITE_DIR="$2"
            shift 2
            ;;
        --project)
            PROJECT_TARGET="$2"
            shift 2
            ;;
        --hosting-site)
            HOSTING_SITE_ID="$2"
            shift 2
            ;;
        --include-fits)
            INCLUDE_FITS=1
            shift
            ;;
        --build-only)
            BUILD_ONLY=1
            shift
            ;;
        -h|--help)
            usage
            exit 0
            ;;
        -*)
            echo "Unknown option: $1" >&2
            usage >&2
            exit 2
            ;;
        *)
            POSITIONAL+=("$1")
            shift
            ;;
    esac
done

if [[ ${#POSITIONAL[@]} -gt 1 ]]; then
    echo "Too many positional arguments: ${POSITIONAL[*]}" >&2
    usage >&2
    exit 2
fi

if [[ ${#POSITIONAL[@]} -eq 1 ]]; then
    REPORT_DIR="${POSITIONAL[0]}"
fi

if [[ ! -d "${REPORT_DIR}" ]]; then
    echo "Report directory not found: ${REPORT_DIR}" >&2
    exit 1
fi
REPORT_DIR="$(cd "${REPORT_DIR}" && pwd)"

if [[ -z "${SLUG}" ]]; then
    SLUG="$(basename "${REPORT_DIR}")"
fi

BUILD_ARGS=(
    --report-dir "${REPORT_DIR}"
    --site-dir "${SITE_DIR}"
    --slug "${SLUG}"
)
if [[ ${INCLUDE_FITS} -eq 1 ]]; then
    BUILD_ARGS+=(--include-fits)
fi

"${PYTHON_BIN}" "${SCRIPT_DIR}/build-ao-web-report.py" "${BUILD_ARGS[@]}"

if [[ ${BUILD_ONLY} -eq 1 ]]; then
    "${PYTHON_BIN}" - "${SITE_DIR}/public/${SLUG}" <<'PY'
import pathlib, sys
d = pathlib.Path(sys.argv[1])
files = [p for p in d.iterdir() if p.is_file()]
tot = sum(p.stat().st_size for p in files)
print(f"[publish-ao-report] Build-only summary: {len(files)} files, {tot / 1048576:.2f} MiB")
PY
    exit 0
fi

if [[ -z "${PROJECT_TARGET}" && -f "${SITE_DIR}/.firebaserc" ]]; then
    PROJECT_TARGET="$("${PYTHON_BIN}" - "${SITE_DIR}/.firebaserc" <<'PY'
import json, sys
try:
    data = json.load(open(sys.argv[1], encoding="utf-8"))
    print(data.get("projects", {}).get("default", ""))
except Exception:
    pass
PY
)"
fi

if [[ -z "${PROJECT_TARGET}" ]]; then
    echo "Error: specify --project <gcp-project> or set FIREBASE_PROJECT" >&2
    exit 2
fi

find_firebase_bin() {
    if [[ -n "${FIREBASE_BIN:-}" && -x "${FIREBASE_BIN}" ]]; then
        printf '%s\n' "${FIREBASE_BIN}"
        return 0
    fi
    if command -v firebase >/dev/null 2>&1; then
        command -v firebase
        return 0
    fi
    if [[ -x "${HOME}/.local/bin/firebase" ]]; then
        printf '%s\n' "${HOME}/.local/bin/firebase"
        return 0
    fi
    return 1
}

if ! FB_BIN="$(find_firebase_bin)"; then
    echo "Firebase CLI binary not found (checked FIREBASE_BIN, PATH, ~/.local/bin/firebase)." >&2
    exit 1
fi

if ! PROJ_JSON="$("${FB_BIN}" projects:list --json --non-interactive 2>/dev/null)"; then
    echo "Firebase authentication required." >&2
    echo "Run: ${FB_BIN} login --no-localhost" >&2
    exit 2
fi

RESOLVED_PROJECT_ID="$("${PYTHON_BIN}" - "${PROJECT_TARGET}" "${PROJ_JSON}" <<'PY'
import json, sys
target = sys.argv[1].strip().lower()
data = json.loads(sys.argv[2])
items = data.get("result", data) if isinstance(data, dict) else data
if not isinstance(items, list):
    items = []
for proj in items:
    pid = str(proj.get("projectId", ""))
    dname = str(proj.get("displayName", ""))
    if pid.lower() == target or dname.lower() == target:
        print(pid)
        break
PY
)"

if [[ -z "${RESOLVED_PROJECT_ID}" ]]; then
    CAND_ID="$(printf '%s' "${PROJECT_TARGET}" \
        | tr '[:upper:]' '[:lower:]' | sed 's/[^a-z0-9-]/-/g')"
    echo "[publish-ao-report] Project '${PROJECT_TARGET}' not yet enabled for Firebase."
    echo "[publish-ao-report] Attempting: ${FB_BIN} projects:addfirebase ${CAND_ID}"
    if ADD_OUT="$("${FB_BIN}" projects:addfirebase "${CAND_ID}" --non-interactive 2>&1)"; then
        RESOLVED_PROJECT_ID="${CAND_ID}"
    else
        echo "${ADD_OUT}" >&2
        echo "" >&2
        echo "Could not resolve or attach Firebase to '${PROJECT_TARGET}'." >&2
        echo "Try one of:" >&2
        echo "  1) ${FB_BIN} projects:addfirebase" >&2
        echo "  2) ${FB_BIN} projects:create ${CAND_ID} --display-name \"${PROJECT_TARGET}\"" >&2
        echo "  3) $0 --project <exact-gcp-project-id>" >&2
        exit 1
    fi
fi

echo "[publish-ao-report] Using Firebase project: ${RESOLVED_PROJECT_ID}"

SITES_JSON="$("${FB_BIN}" hosting:sites:list --project "${RESOLVED_PROJECT_ID}" \
    --json --non-interactive 2>/dev/null || echo '{"result":{"sites":[]}}')"

RESOLVED_SITE_ID="$("${PYTHON_BIN}" - "${HOSTING_SITE_ID}" "${SITES_JSON}" <<'PY'
import json, sys
wanted = sys.argv[1].strip()
data = json.loads(sys.argv[2])
res = data.get("result", data) if isinstance(data, dict) else data
sites = res.get("sites", res) if isinstance(res, dict) else res
if not isinstance(sites, list):
    sites = []
ids = []
for s in sites:
    sid = str(s.get("siteId") or str(s.get("name", "")).split("/")[-1])
    if sid:
        ids.append(sid)
if wanted:
    print(wanted if wanted in ids else "")
elif ids:
    print(ids[0])
PY
)"

if [[ -z "${RESOLVED_SITE_ID}" ]]; then
    if [[ -n "${HOSTING_SITE_ID}" ]]; then
        SITE_CAND="${HOSTING_SITE_ID}"
        "${FB_BIN}" hosting:sites:create "${SITE_CAND}" \
            --project "${RESOLVED_PROJECT_ID}" --non-interactive
        RESOLVED_SITE_ID="${SITE_CAND}"
    else
        SITE_CAND="${RESOLVED_PROJECT_ID}"
        if ! "${FB_BIN}" hosting:sites:create "${SITE_CAND}" \
            --project "${RESOLVED_PROJECT_ID}" --non-interactive 2>/dev/null; then
            SITE_CAND="${RESOLVED_PROJECT_ID}-ao"
            "${FB_BIN}" hosting:sites:create "${SITE_CAND}" \
                --project "${RESOLVED_PROJECT_ID}" --non-interactive
        fi
        RESOLVED_SITE_ID="${SITE_CAND}"
    fi
fi

echo "[publish-ao-report] Using Hosting site: ${RESOLVED_SITE_ID}"

"${PYTHON_BIN}" "${SCRIPT_DIR}/build-ao-web-report.py" "${BUILD_ARGS[@]}" \
    --project "${RESOLVED_PROJECT_ID}" --site-id "${RESOLVED_SITE_ID}"

(
    cd "${SITE_DIR}"
    "${FB_BIN}" deploy --only hosting \
        --project "${RESOLVED_PROJECT_ID}" --non-interactive
)

echo ""
echo "[publish-ao-report] Live URLs:"
echo "  Root   : https://${RESOLVED_SITE_ID}.web.app/"
echo "  Report : https://${RESOLVED_SITE_ID}.web.app/${SLUG}/"
