#!/usr/bin/env bash
# ==============================================================================
# AI INTERVIEW STUDIO — HARDENED STAGING TEARDOWN SCRIPT
# Environment: STAGING ONLY (Strictly protected against accidental production deletion)
# ==============================================================================

set -euo pipefail

PROJECT_ID="${1:-}"
if [ -z "$PROJECT_ID" ]; then
  echo "Error: Google Cloud Project ID required."
  echo "Usage: ./gcp_staging_teardown.sh <PROJECT_ID>"
  exit 1
fi

# ==============================================================================
# CRITICAL SAFETY GUARDS (PRODUCTION PROTECTION)
# ==============================================================================

# Guard 1: Block any project containing 'prod' or 'production' in the name
PROJECT_LOWER=$(echo "$PROJECT_ID" | tr '[:upper:]' '[:lower:]')
if [[ "$PROJECT_LOWER" =~ prod|production|prd ]]; then
  echo "======================================================================"
  echo "CRITICAL SECURITY ERROR: PRODUCTION PROJECT DETECTED ($PROJECT_ID)"
  echo "This teardown script is strictly hardcoded for STAGING environments."
  echo "Execution has been aborted immediately to prevent accidental data loss."
  echo "======================================================================"
  exit 1
fi

# Guard 2: Require explicit typed confirmation string
echo "======================================================================"
echo "WARNING: This script will DESTROY all AI Interview Studio STAGING resources"
echo "in project: ${PROJECT_ID}"
echo "======================================================================"
read -r -p "Type 'DESTROY_STAGING_CONFIRM' to proceed: " CONFIRMATION

if [ "$CONFIRMATION" != "DESTROY_STAGING_CONFIRM" ]; then
  echo "Confirmation string did not match. Aborting teardown."
  exit 1
fi

echo "Proceeding with staging teardown..."

REGION="${2:-us-central1}"
DB_INSTANCE="ai-interview-staging-db"
REPO_NAME="ai-interview-staging-repo"

# 1. Delete Cloud Run Staging Services
echo "[1/5] Deleting Cloud Run staging services..."
gcloud run services delete ai-interview-studio-frontend-staging --region="${REGION}" --project="${PROJECT_ID}" --quiet || true
gcloud run services delete ai-interview-studio-backend-staging --region="${REGION}" --project="${PROJECT_ID}" --quiet || true

# 2. Delete Staging Cloud SQL Instance
echo "[2/5] Deleting Staging Cloud SQL instance..."
gcloud sql instances delete "${DB_INSTANCE}" --project="${PROJECT_ID}" --quiet || true

# 3. Delete Staging Artifact Registry
echo "[3/5] Deleting Staging Artifact Registry repository..."
gcloud artifacts repositories delete "${REPO_NAME}" --location="${REGION}" --project="${PROJECT_ID}" --quiet || true

# 4. Delete Staging Secrets
echo "[4/5] Deleting Staging Secrets in Secret Manager..."
for secret in ai-studio-staging-db-url ai-studio-staging-jwt-secret ai-studio-staging-super-admin-password ai-studio-staging-gemini-api-key ai-studio-staging-groq-api-key ai-studio-staging-resend-api-key; do
  gcloud secrets delete "$secret" --project="${PROJECT_ID}" --quiet || true
done

# 5. Delete Staging Service Accounts
echo "[5/5] Deleting Staging Service Accounts..."
gcloud iam service-accounts delete "sa-backend-staging@${PROJECT_ID}.iam.gserviceaccount.com" --project="${PROJECT_ID}" --quiet || true
gcloud iam service-accounts delete "sa-frontend-staging@${PROJECT_ID}.iam.gserviceaccount.com" --project="${PROJECT_ID}" --quiet || true

echo "Staging environment teardown complete."
