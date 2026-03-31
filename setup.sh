#!/usr/bin/env bash
# setup.sh — Bootstrap the GCP project for the ADK Summarizer Agent.
#
# Run once before your first deployment:
#   chmod +x setup.sh
#   ./setup.sh YOUR_PROJECT_ID us-central1
#
# What this script does:
#   1. Enables required GCP APIs
#   2. Creates an Artifact Registry repository
#   3. Creates a least-privilege service account for Cloud Run
#   4. Grants IAM roles to the service account
#   5. Creates a Cloud Build trigger (push to main → deploy)
# ─────────────────────────────────────────────────────────────────────────────

set -euo pipefail

PROJECT_ID="${1:?Usage: ./setup.sh PROJECT_ID [REGION]}"
REGION="${2:-us-central1}"
SERVICE_NAME="adk-summarizer-agent"
SA_NAME="${SERVICE_NAME}-sa"
SA_EMAIL="${SA_NAME}@${PROJECT_ID}.iam.gserviceaccount.com"
REPO_NAME="cloud-run-agents"

echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "  ADK Summarizer Agent — GCP Bootstrap"
echo "  Project : ${PROJECT_ID}"
echo "  Region  : ${REGION}"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

gcloud config set project "${PROJECT_ID}"

# ── 1. Enable APIs ─────────────────────────────────────────────────────────────
echo ""
echo "▶ Enabling GCP APIs…"
gcloud services enable \
    run.googleapis.com \
    cloudbuild.googleapis.com \
    artifactregistry.googleapis.com \
    aiplatform.googleapis.com \
    iam.googleapis.com \
    logging.googleapis.com \
    --project="${PROJECT_ID}"

echo "  ✓ APIs enabled"

# ── 2. Artifact Registry repository ───────────────────────────────────────────
echo ""
echo "▶ Creating Artifact Registry repository: ${REPO_NAME}…"
if gcloud artifacts repositories describe "${REPO_NAME}" \
       --location="${REGION}" --project="${PROJECT_ID}" &>/dev/null; then
    echo "  ✓ Repository already exists, skipping."
else
    gcloud artifacts repositories create "${REPO_NAME}" \
        --repository-format=docker \
        --location="${REGION}" \
        --description="Docker images for Cloud Run agents" \
        --project="${PROJECT_ID}"
    echo "  ✓ Repository created"
fi

# ── 3. Service account ─────────────────────────────────────────────────────────
echo ""
echo "▶ Creating service account: ${SA_NAME}…"
if gcloud iam service-accounts describe "${SA_EMAIL}" \
       --project="${PROJECT_ID}" &>/dev/null; then
    echo "  ✓ Service account already exists, skipping."
else
    gcloud iam service-accounts create "${SA_NAME}" \
        --display-name="ADK Summarizer Agent — Cloud Run SA" \
        --project="${PROJECT_ID}"
    echo "  ✓ Service account created: ${SA_EMAIL}"
fi

# ── 4. IAM bindings (least-privilege) ─────────────────────────────────────────
echo ""
echo "▶ Binding IAM roles to service account…"

# Allow the SA to call Vertex AI
gcloud projects add-iam-policy-binding "${PROJECT_ID}" \
    --member="serviceAccount:${SA_EMAIL}" \
    --role="roles/aiplatform.user" \
    --condition=None --quiet

# Allow the SA to write Cloud Logging
gcloud projects add-iam-policy-binding "${PROJECT_ID}" \
    --member="serviceAccount:${SA_EMAIL}" \
    --role="roles/logging.logWriter" \
    --condition=None --quiet

echo "  ✓ IAM roles granted"

# ── 5. Cloud Build service account permissions ─────────────────────────────────
echo ""
echo "▶ Granting Cloud Build SA permissions to deploy Cloud Run…"
CB_SA="$(gcloud projects describe "${PROJECT_ID}" \
    --format='value(projectNumber)')@cloudbuild.gserviceaccount.com"

for role in roles/run.admin roles/iam.serviceAccountUser roles/artifactregistry.writer; do
    gcloud projects add-iam-policy-binding "${PROJECT_ID}" \
        --member="serviceAccount:${CB_SA}" \
        --role="${role}" \
        --condition=None --quiet
done
echo "  ✓ Cloud Build permissions set"

# ── 6. Cloud Build trigger ─────────────────────────────────────────────────────
echo ""
echo "▶ Creating Cloud Build trigger (push to main)…"
echo "  NOTE: Connect your GitHub repo to Cloud Build first via the Console:"
echo "  https://console.cloud.google.com/cloud-build/triggers/connect"
echo ""
echo "  Then run:"
echo "  gcloud builds triggers create github \\\"
echo "    --repo-name=YOUR_REPO_NAME \\\"
echo "    --repo-owner=YOUR_GITHUB_ORG \\\"
echo "    --branch-pattern='^main$' \\\"
echo "    --build-config=cloudbuild.yaml \\\"
echo "    --name=${SERVICE_NAME}-trigger \\\"
echo "    --project=${PROJECT_ID}"

# ── Done ───────────────────────────────────────────────────────────────────────
echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "  Bootstrap complete! Next steps:"
echo ""
echo "  1. Copy .env.example → .env and set GOOGLE_CLOUD_PROJECT=${PROJECT_ID}"
echo ""
echo "  2. First manual deploy:"
echo "     gcloud builds submit \\\"
echo "       --config=cloudbuild.yaml \\\"
echo "       --substitutions=_REGION=${REGION},_SERVICE_NAME=${SERVICE_NAME} \\\"
echo "       --project=${PROJECT_ID}"
echo ""
echo "  3. Get your service URL:"
echo "     gcloud run services describe ${SERVICE_NAME} \\\"
echo "       --region=${REGION} --format='value(status.url)'"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
