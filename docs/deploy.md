# Deploy: doc2json.pl

The landing (`frontend/`, static nginx) runs on the team VPS next to the faktczyfejk.pl demo (repo HackNation2026).

## Server

- OVHcloud VPS-2, Ubuntu 24.04, IPv4 135.125.239.206. Login: `ssh -i ~/.ssh/faktczyfejk ubuntu@135.125.239.206`
  (key on Michał's Mac; never commit keys).
- Docker Compose stacks live in `/opt/<name>`. This repo: `/opt/doc2json`, Compose project `doc2json`.
- HTTPS: one Caddy container, owned by the faktczyfejk stack (`/opt/faktczyfejk`, checkout of HackNation2026
  branch `prod`, reset every minute by a systemd timer). It holds ports 80/443 and issues Let's Encrypt certificates.
  Caddy config changes only through the HackNation2026 repo (PR → `main` → `prod`), never by hand on the server.
- Shared Docker network `edge` (created once with `docker network create edge`). `doc2json-web` joins it and
  publishes no ports; Caddy reaches it as `doc2json-web:80`.

## Deploy this repo

```bash
rsync -az --delete -e "ssh -i ~/.ssh/faktczyfejk" compose.prod.yaml frontend ubuntu@135.125.239.206:/opt/doc2json/
ssh -i ~/.ssh/faktczyfejk ubuntu@135.125.239.206 'cd /opt/doc2json && docker compose -f compose.prod.yaml up -d --build --wait'
```

Check from inside the network: `docker run --rm --network edge alpine:3.20 wget -qO- http://doc2json-web/`.

## Going public (pending on 21.11.2026)

1. Domain doc2json.pl: ordered at OVH (order 263873856), payment in validation. Once active, in the OVH DNS zone:
   A records for `doc2json.pl` and `www.doc2json.pl` → 135.125.239.206, no AAAA (same reason as faktczyfejk.pl:
   IPv6 clients behind Docker's proxy would share one rate-limit key).
2. HackNation2026 PR (needs the team's go, it touches the live demo): Caddy joins the external `edge` network and the
   Caddyfile gets `doc2json.pl { reverse_proxy doc2json-web:80 }` plus a `www.doc2json.pl` redirect. Caddy then
   reloads and issues the certificate.
3. When the extraction backend exists: add it to `compose.prod.yaml` and proxy `/api/` to it in
   `frontend/nginx.conf`. Until then `/api/` returns 404 and the page keeps files in the browser.
