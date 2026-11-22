# Deploy: doc2json.pl

The landing (`frontend/`, static nginx) runs on the team VPS next to the faktczyfejk.pl demo (repo HackNation2026).

## Server

- OVHcloud VPS-2, Ubuntu 24.04, IPv4 135.125.239.206. Login: `ssh -i ~/.ssh/faktczyfejk ubuntu@135.125.239.206`
  (key held by the deployment operator; never commit keys).
- Docker Compose stacks live in `/opt/<name>`. This repo: `/opt/doc2json`, Compose project `doc2json`.
- HTTPS: one Caddy container, owned by the faktczyfejk stack (`/opt/faktczyfejk`, checkout of HackNation2026
  branch `prod`, reset every minute by a systemd timer). It holds ports 80/443 and issues Let's Encrypt certificates.
  Caddy config changes only through the HackNation2026 repo (PR → `main` → `prod`), never by hand on the server.
- Shared Docker network `edge` (created once with `docker network create edge`). `doc2json-web` joins it and
  publishes no ports; Caddy reaches it as `doc2json-web:80`.

## Deploy this repo

```bash
rsync -az --delete -e "ssh -i ~/.ssh/faktczyfejk" compose.prod.yaml api.Dockerfile .dockerignore requirements.txt kio2json config frontend ubuntu@135.125.239.206:/opt/doc2json/
ssh -i ~/.ssh/faktczyfejk ubuntu@135.125.239.206 'cd /opt/doc2json && docker compose -f compose.prod.yaml up -d --build --wait'
```

Check from inside the network: `docker run --rm --network edge alpine:3.20 wget -qO- http://doc2json-web/`.

## Going public

1. Done 21.11.2026: domain doc2json.pl at OVH; in its OVH DNS zone
   A records for `doc2json.pl` and `www.doc2json.pl` → 135.125.239.206, no AAAA (same reason as faktczyfejk.pl:
   IPv6 clients behind Docker's proxy would share one rate-limit key).
2. Done 21.11.2026 live on the server, HackNation2026 PR #48 merged to main, not yet on `prod`: Caddy joins the external `edge` network and the
   Caddyfile gets `doc2json.pl { reverse_proxy doc2json-web:80 }` plus a `www.doc2json.pl` redirect. Caddy then
   reloads and issues the certificate.
3. Extraction: `doc2json-api` (`api.Dockerfile`, FastAPI app `kio2json.web_api`, OpenAPI docs at `/api/docs`;
   installs `requirements.txt` like the jury)
   runs the rules engine without model keys, one document at a time (max 10 files x 20 MB, 90 s per document),
   capped at 2 CPUs and 3 GB. nginx in
   `doc2json-web` proxies `/api/` to it; if it is down, the page says so and keeps the files in the browser.
