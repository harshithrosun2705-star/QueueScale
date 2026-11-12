#!/usr/bin/env bash
set -euo pipefail

namespace=${1:?Usage: scripts/bootstrap-secrets.sh NAMESPACE}
kubectl create namespace "$namespace" --dry-run=client -o yaml | kubectl apply -f -
if [[ -n $(kubectl -n "$namespace" get secret queuescale-secrets --ignore-not-found -o name) ]]; then
    echo "Using existing queuescale-secrets in $namespace"
    exit 0
fi

# Hex values can be used directly in both connection URLs.
pg_password=$(openssl rand -hex 24)
mq_password=$(openssl rand -hex 24)
kubectl -n "$namespace" create secret generic queuescale-secrets \
    --from-literal="POSTGRES_PASSWORD=$pg_password" \
    --from-literal="RABBITMQ_PASSWORD=$mq_password" \
    --from-literal="DATABASE_URL=postgresql://queuescale:$pg_password@postgres:5432/queuescale" \
    --from-literal="AMQP_URL=amqp://queuescale:$mq_password@rabbitmq:5672/"
