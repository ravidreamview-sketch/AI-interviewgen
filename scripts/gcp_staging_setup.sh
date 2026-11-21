#!/usr/bin/env bash
# ==============================================================================
# AI INTERVIEW STUDIO — GOOGLE CLOUD STAGING PROVISIONING SCRIPT
# Environment: STAGING ONLY
# Region: asia-south1
# ==============================================================================

set -euo pipefail

# 1. Configuration Parameters (Pass via arguments or prompt)
PROJECT_ID="${1:-}"
if [ -z "$PROJECT_ID" ]; then
  echo "Error: Please provide your Google Cloud Project ID as the first argument."
  echo "Usage: ./gcp_staging_setup.sh <PROJECT_ID> [REGION]"
  exit 1
fi

REGION="${2:-asia-south1}"
REPO_NAME="ai-interview-staging-repo"
DB_INSTANCE="ai-interview-staging-db"
DB_NAME="ai_interview_staging"
DB_USER="interview_staging_user"
BACKEND_SA="sa-backend-staging@${PROJECT_ID}.iam.gserviceaccount.com"
FRONTEND_SA="sa-frontend-staging@${PROJECT_ID}.iam.gserviceaccount.com"

echo "=========================================================="
echo "AI Interview Studio — GCP Staging Environment Setup"
echo "Project:  ${PROJECT_ID}"
echo "Region:   ${REGION}"
echo "=========================================================="

# 2. Enable Required APIs
echo "[1/7] Enabling Required Google Cloud APIs..."
gcloud services enable \
  run.googleapis.com \
  sqladmin.googleapis.com \
  secretmanager.googleapis.com \
  artifactregistry.googleapis.com \
  cloudbuild.googleapis.com \
  logging.googleapis.com \
  monitoring.googleapis.com \
  --project="${PROJECT_ID}"

# 3. Create Artifact Registry
echo "[2/7] Creating Artifact Registry Repository..."
if ! gcloud artifacts repositories describe "${REPO_NAME}" --location="${REGION}" --project="${PROJECT_ID}" &>/dev/null; then
  gcloud artifacts repositories create "${REPO_NAME}" \
    --repository-format=docker \
    --location="${REGION}" \
    --description="AI Interview Studio staging container images" \
    --project="${PROJECT_ID}"
fi

# 4. Create Service Accounts and Assign IAM Roles
echo "[3/7] Setting up Service Accounts and IAM Policies..."
if ! gcloud iam service-accounts describe "${BACKEND_SA}" --project="${PROJECT_ID}" &>/dev/null; then
  gcloud iam service-accounts create "sa-backend-staging" \
    --display-name="AI Interview Studio Staging Backend SA" \
    --project="${PROJECT_ID}"
fi

if ! gcloud iam service-accounts describe "${FRONTEND_SA}" --project="${PROJECT_ID}" &>/dev/null; then
  gcloud iam service-accounts create "sa-frontend-staging" \
    --display-name="AI Interview Studio Staging Frontend SA" \
    --project="${PROJECT_ID}"
fi

# Grant Cloud SQL client and Secret Manager access to backend SA
gcloud projects add-iam-policy-binding "${PROJECT_ID}" \
  --member="serviceAccount:${BACKEND_SA}" \
  --role="roles/cloudsql.client" \
  --condition=None

gcloud projects add-iam-policy-binding "${PROJECT_ID}" \
  --member="serviceAccount:${BACKEND_SA}" \
  --role="roles/secretmanager.secretAccessor" \
  --condition=None

gcloud projects add-iam-policy-binding "${PROJECT_ID}" \
  --member="serviceAccount:${BACKEND_SA}" \
  --role="roles/logging.logWriter" \
  --condition=None

gcloud projects add-iam-policy-binding "${PROJECT_ID}" \
  --member="serviceAccount:${FRONTEND_SA}" \
  --role="roles/logging.logWriter" \
  --condition=None

echo "Staging environment preparation script ready. Database provisioning proceeds in G3."
