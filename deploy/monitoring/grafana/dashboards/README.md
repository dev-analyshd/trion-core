# TRION Grafana dashboards

Grafana (docker compose `grafana` service) provisions every JSON dashboard
in this directory read-only at boot. **No dashboards are defined yet** —
this directory exists so the compose bind mount is real. Add dashboards by
exporting JSON from a Grafana instance into this folder.

Until a dashboard lands, Grafana is reachable on `127.0.0.1:3001` (admin /
`$GRAFANA_PASSWORD`, default `admin`) with an empty library. Prometheus
itself only exposes the `up` metric per scrape job right now: neither the
Flask API nor the FAISS service implements a `/metrics` endpoint, and the
trion_* metrics the alert rules reference do not exist anywhere yet (see
deploy/monitoring/prometheus.yml and alerts.yml notes).
