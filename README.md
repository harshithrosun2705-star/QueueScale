# QueueScale

**Fault-Tolerant Document Processing with Kubernetes Autoscaling and GitOps**

QueueScale accepts scanned forms and extracts their text in background workers. During an upload surge, the API can keep accepting jobs while Kubernetes adds workers based on the RabbitMQ backlog. A worker crash can cause redelivery, and a job still has one stored result.

## How a job runs

1. FastAPI validates a PNG or JPEG upload, stores it in PostgreSQL, and returns HTTP `202 Accepted` with a job ID. The jobs table also acts as the transactional outbox.
2. The dispatcher locks a pending job, publishes its ID and attempt number to a durable RabbitMQ queue, waits for a publisher confirmation, then marks the row queued.
3. A worker locks the job row, extracts text with Tesseract, and commits the result before acknowledging the message. Redelivery skips completed jobs and stale attempts.
4. An OCR error schedules a retry after 2 or 4 seconds. The third unsuccessful attempt marks the job failed. A process crash before commit leaves the attempt available for redelivery.
5. KEDA scales the worker deployment from one to six replicas using queue length. Kubernetes gives terminating workers up to 75 seconds to finish.

If the dispatcher crashes after RabbitMQ confirms a publish but before the database commit, it can publish the same job again. The row lock, status, and attempt number make duplicate deliveries safe. The source image is cleared from the database when a job completes or fails.

## Run locally with Docker Compose

Install Docker with Compose v2 and Python 3. Run from the project root.

```bash
docker build -t queuescale:local .
docker compose up -d --wait
python3 scripts/smoke.py --negative-tests
```

Open [API documentation](http://localhost:8000/docs) to submit a scan and look up its job ID. The smoke test uploads a sample, verifies the recognized text, checks unsupported-file handling, and confirms that corrupt images reach a terminal failure after three attempts.

```bash
curl -F file=@samples/sample-form.png http://localhost:8000/jobs
curl http://localhost:8000/jobs/YOUR_JOB_ID
```

Run the worker recovery demo separately. The delay gives the script time to terminate the worker after PostgreSQL commits the OCR result and before RabbitMQ receives the acknowledgment.

```bash
DEMO_ACK_DELAY_SECONDS=30 docker compose up -d --wait worker
scripts/check-worker-recovery.sh
docker compose up -d worker
```

A successful run prints `Verified committed result survived worker termination and redelivery.` The script checks the replacement worker's log for a redelivery and verifies that the result and attempt count stayed intact.

Stop the services with `docker compose down`. Use `docker compose down --volumes` if you want to delete local demo jobs and queue data as well.

## GitHub Actions and Argo CD

1. Push the project to `main` with GitHub Actions enabled. **Test and release** builds the application image, tests it against PostgreSQL and RabbitMQ, exercises worker recovery, and runs Trivy. On `main`, it publishes the tested image to GHCR and updates the staging overlay with its immutable digest. Trivy blocks the release for fixable HIGH or CRITICAL findings.
2. Allow the workflow to push manifest commits to `main`. If branch rules require PRs, use the digest in the workflow summary to make the staging manifest change through a PR. The same applies to the promotion change. For the local cluster, make the GHCR package public or configure an image pull secret in both namespaces.
3. Create a local cluster with `kind`, and install KEDA and Argo CD. Then bootstrap the staging namespace and register the staging application. Wait for the first release to set a staging digest before syncing.

   ```bash
   kind create cluster --name queuescale
   helm repo add kedacore https://kedacore.github.io/charts
   helm repo add argo https://argoproj.github.io/argo-helm
   helm repo update
   helm upgrade --install keda kedacore/keda --namespace keda --create-namespace --wait
   helm upgrade --install argocd argo/argo-cd --namespace argocd --create-namespace --wait
   scripts/bootstrap-secrets.sh queuescale-staging
   kubectl apply -f deploy/argocd/staging.yaml
   ```

   For a private GitHub repository, configure repository access in Argo CD before registering the application. Both overlays track `main`.

4. Wait for the staging application to show Synced and Healthy in Argo CD, then run a smoke test against it. Port forwarding runs in a separate terminal.

   ```bash
   kubectl -n queuescale-staging rollout status deployment/api --timeout=180s
   kubectl -n queuescale-staging get deployment api -o jsonpath='{.spec.template.spec.containers[0].image}'
   kubectl -n queuescale-staging port-forward svc/api 8000:8000
   # In another terminal, from the project root
   python3 scripts/smoke.py --negative-tests
   ```

5. Copy the `sha256:...` portion of the deployed staging image printed above. In Actions, manually run **Promote verified staging image** with that digest. The workflow compares it to the current staging digest and commits it to the demo-production overlay. Register the demo-production application after the first promotion. Argo CD then syncs the namespace. To roll back after a subsequent release, restore the previous known-good digest in Git.

   ```bash
   scripts/bootstrap-secrets.sh queuescale-production
   kubectl apply -f deploy/argocd/demo-production.yaml
   kubectl -n queuescale-production rollout status deployment/api --timeout=180s
   ```

For a Kubernetes demo using a locally built application image, install KEDA as above and run:

```bash
docker build -t queuescale:local .
kind load docker-image queuescale:local --name queuescale
scripts/bootstrap-secrets.sh queuescale-local
kubectl apply -k deploy/base -n queuescale-local
```

## Show worker autoscaling

In staging, keep the API port-forward active and watch the worker deployment and HPA while submitting a burst of scans.

```bash
kubectl -n queuescale-staging get hpa,deployment -w
```

```bash
python3 scripts/smoke.py --jobs 300 --timeout 300
```

Record the elapsed time and peak number of worker replicas. Increase the batch size if the backlog clears before the autoscaler samples it. For a fixed-worker comparison, temporarily remove the ScaledObject in a local demo namespace without Argo CD reconciliation, set the worker deployment to one replica, and repeat the same burst on the same cluster.

## Repository layout

| Path | Purpose |
| --- | --- |
| `queuescale/` | FastAPI app, PostgreSQL schema, dispatcher, RabbitMQ helpers, and OCR worker |
| `deploy/base/` | Shared Kubernetes deployments, services, persistent storage, and KEDA config |
| `deploy/overlays/` | Staging and demo-production image references and namespaces |
| `deploy/argocd/` | Argo CD application definitions |
| `.github/workflows/` | Build, test, scan, release, and promote workflows |
| `scripts/` | Smoke test, worker recovery check, and Kubernetes secret setup |
| `tests/`, `samples/` | Unit tests and a synthetic sample scan |
| `Dockerfile`, `compose.yaml` | Local image and development stack |

This demo uses single-node PostgreSQL and RabbitMQ instances, isolated namespaces, and English OCR for PNG/JPEG scans. Its failure demonstration covers worker crashes and message redelivery. Use synthetic scans for the local demo.
