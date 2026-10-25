# Deploying Spool Maker

The image runs the app under gunicorn on port 5009 as a non-root user. Commands are shown for podman; docker takes the same arguments (`docker build`, `docker run`, `docker compose`).

```
podman build --format docker -t spoolmaker .
podman run -d --name spoolmaker -p 127.0.0.1:5009:5009 --restart unless-stopped spoolmaker
```

`--format docker` keeps the image's `HEALTHCHECK` (it polls `/healthz`); podman's default OCI format drops it with a warning. Docker builds need no flag. Rootless podman can publish port 5009 (or any port from 1024 up) without extra setup. Or with compose (`podman compose` uses docker-compose or podman-compose, whichever is installed):

```
podman compose up -d --build
```

Rootless podman has no daemon, so `--restart` (and compose's `restart:`) only takes effect while podman is running: after a reboot, containers come back only if the user's `podman-restart.service` is enabled (`systemctl --user enable podman-restart.service`, plus `loginctl enable-linger $USER` so it starts without a login). Alternatively run it as a systemd service with a quadlet, `~/.config/containers/systemd/spoolmaker.container`:

```
[Container]
Image=localhost/spoolmaker:latest
PublishPort=127.0.0.1:5009:5009
Environment=WEB_CONCURRENCY=2

[Service]
Restart=always

[Install]
WantedBy=default.target
```

then `systemctl --user daemon-reload && systemctl --user start spoolmaker` (again with lingering enabled).

Settings (environment variables):

- `WEB_CONCURRENCY` - gunicorn workers (default 2). Each worker keeps its own cache of built models.
- `PORT` - listen port inside the container (default 5009).
- `TRUST_PROXY` - `1` (the image default) trusts one proxy hop's `X-Forwarded-For`, `-Proto`, `-Host` and `-Prefix` headers (`-Prefix` is ignored when `BASE_PATH` is set, and only a plain path such as `/spool` is accepted). Only safe when the app is reachable solely through that proxy, which must set or strip these headers; keep the published port bound to `127.0.0.1` (as above) and set `TRUST_PROXY=0` if clients can reach the app directly.
- `BASE_PATH` - see below.

## Under a sub-path (e.g. n2g.dev/spool/)

Every URL in the page is relative, so the app works at `/` or under any prefix. The usual setup is a proxy that strips the prefix; sending `X-Forwarded-Prefix` as well lets the server add a `<base href>` so the page also works when opened without the trailing slash. Without the header the page still works at `/spool/` (its URLs resolve against the page's own address). nginx:

```
location = /spool { return 301 /spool/; }
location /spool/ {
    proxy_pass http://127.0.0.1:5009/;      # trailing slash strips /spool
    proxy_set_header Host $host;
    proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    proxy_set_header X-Forwarded-Proto $scheme;
    proxy_set_header X-Forwarded-Host $host;
    proxy_set_header X-Forwarded-Prefix /spool;
    client_max_body_size 1m;
}
```

Caddy:

```
n2g.dev {
    redir /spool /spool/
    handle_path /spool/* {
        reverse_proxy 127.0.0.1:5009 {
            header_up X-Forwarded-Prefix /spool
        }
    }
}
```

Redirect `/spool` to `/spool/` as shown. With `X-Forwarded-Prefix` the page also loads without the slash (the `<base>` tag pins its URLs); without the header the redirect is required.

If the proxy forwards the full path instead (`/spool/api/...` reaches the app unchanged), set `BASE_PATH=/spool` (for example `podman run -e BASE_PATH=/spool ...`); the app then serves under `/spool/` and still answers `/healthz` at the root. Clear any client-sent prefix header at the proxy:

```
location /spool/ {
    proxy_pass http://127.0.0.1:5009;       # no trailing slash: the path stays /spool/...
    proxy_set_header Host $host;
    proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    proxy_set_header X-Forwarded-Proto $scheme;
    proxy_set_header X-Forwarded-Host $host;
    proxy_set_header X-Forwarded-Prefix "";
}
```

There is no rate limiting in the app. Each request's CPU time is bounded (a model build takes well under a second), but if the site is public, add limits at the proxy, e.g. nginx `limit_req_zone $binary_remote_addr zone=spool:10m rate=5r/s;` with `limit_req zone=spool burst=20;` in the location.
