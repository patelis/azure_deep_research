#!/usr/bin/env bash
# One-time GitHub -> Azure trust (keyless OIDC) for the deploy workflow. A privileged bootstrap,
# deliberately OUTSIDE the workload IaC (separation of duties). Run locally once.
#
#   az login
#   utils/setup-github-oidc.sh <owner/repo> <environment>      # e.g. patelis/azure_deep_research dev
#
# Creates an Entra app registration + service principal with a federated credential for the repo's
# GitHub Environment, grants it Contributor + RBAC roles on the subscription, and prints the
# variables/secrets to set on the GitHub repo (Environment-scoped).
set -euo pipefail

REPO="${1:?usage: setup-github-oidc.sh <owner/repo> <environment>}"
ENVIRONMENT="${2:?usage: setup-github-oidc.sh <owner/repo> <environment>}"
APP_NAME="gh-oidc-${REPO//\//-}-${ENVIRONMENT}"

SUBSCRIPTION_ID="$(az account show --query id -o tsv)"
TENANT_ID="$(az account show --query tenantId -o tsv)"

echo "Creating app registration: ${APP_NAME}"
APP_ID="$(az ad app create --display-name "${APP_NAME}" --query appId -o tsv)"
az ad sp create --id "${APP_ID}" >/dev/null 2>&1 || true
SP_OID="$(az ad sp show --id "${APP_ID}" --query id -o tsv)"

echo "Adding federated credential for repo:${REPO}:environment:${ENVIRONMENT}"
az ad app federated-credential create --id "${APP_ID}" --parameters "{
  \"name\": \"${ENVIRONMENT}\",
  \"issuer\": \"https://token.actions.githubusercontent.com\",
  \"subject\": \"repo:${REPO}:environment:${ENVIRONMENT}\",
  \"audiences\": [\"api://AzureADTokenExchange\"]
}" >/dev/null

echo "Granting subscription roles (Contributor, RBAC Administrator)"
for ROLE in "Contributor" "Role Based Access Control Administrator"; do
  az role assignment create --assignee-object-id "${SP_OID}" \
    --assignee-principal-type ServicePrincipal \
    --role "${ROLE}" --scope "/subscriptions/${SUBSCRIPTION_ID}" >/dev/null
done

cat <<EOF

Done. Set these on the GitHub repo's Environment "${ENVIRONMENT}"
(Settings -> Environments -> ${ENVIRONMENT}):

  Variables:
    AZURE_CLIENT_ID=${APP_ID}
    AZURE_TENANT_ID=${TENANT_ID}
    AZURE_SUBSCRIPTION_ID=${SUBSCRIPTION_ID}
    AZURE_PRINCIPAL_ID=${SP_OID}
    AZURE_ENV_NAME=<your azd env name, e.g. dr-${ENVIRONMENT}>
    AZURE_LOCATION=swedencentral
    BUDGET_ALERT_EMAILS=["you@example.com"]   # optional

  Secrets (optional):
    API_KEYS=<name:hash,...>                  # from utils/mint_key.py

  Then run the Deploy workflow against the "${ENVIRONMENT}" environment.
EOF
