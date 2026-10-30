# Hosting Showtime on a server

Showtime runs on any Linux server (a cloud VM or a machine of your own) with Docker and Compose
v2. On the server it sits behind Caddy, which adds HTTPS and one password for the whole app.

## What you need

- A server with Docker, Compose v2, `make` and `git`. About 4 vCPUs and 16 GB RAM is
  comfortable, because the simulations run in Docker on the same machine. Ports 80 and 443 open.
- Your `.env`, working locally (the AI key, and the Tavily key if you use it;
  [PROVIDERS.md](PROVIDERS.md)). On a server, use a hosted AI such as OpenRouter:
  `LLM_PROVIDER=local` needs the llama.cpp server running on that machine's GPU.

A new cloud VM can be set up with `deploy/cloud-init.yaml`: a cloud-init template that installs
Docker, `make` and `git`. Replace `__USER__` with your user name and `__KEY__` with your SSH public
key, then pass it as the VM's user data.

## Steps

1. **Set a password** (the hosted app is public; the password keeps strangers from spending your
   model credit). On your machine or on the server:

   ```bash
   make cloud-password            # asks for a user and a password; stores the bcrypt hash in .env
   ```

   The password needs at least 10 characters and is never stored, only its hash.

2. **Choose the address.** In `.env`, set `SITE_ADDRESS`:
   - a domain, `SITE_ADDRESS=showtime.example.org`: point its DNS at the server first, and Caddy
     gets an HTTPS certificate for it on its own;
   - no domain: `SITE_ADDRESS=<the server's IP>.sslip.io` is a name that already points at that
     IP, so Caddy can get a certificate for it too;
   - `SITE_ADDRESS=:80` (the default): plain HTTP, for a private network only.

   Set `WEB_ORIGIN` to the same public URL (for example `https://showtime.example.org`).

3. **Copy the code and `.env` to the server** (for example `git clone`, then `scp .env`). Keep
   `.env` out of git, and readable by you only (`chmod 600 .env`; `make cloud-password` does this).

4. **Start it** on the server, in the project folder:

   ```bash
   make cloud-up
   ```

   It builds the sandbox image and the app, fetches the incident dataset if `data/` is empty, and
   starts the stack. Give people the address, the user name and the password.

After a change, copy the new code and run `make cloud-up` again. `make cloud-down` stops it.

## What runs on the server

`make cloud-up` uses `docker-compose.yml` plus `docker-compose.cloud.yml`:

- **Caddy** on ports 80 and 443: the only open ports. With a domain in `SITE_ADDRESS` it gets an
  HTTPS certificate on its own. It asks for the password on every page and every API call, and
  streams live test progress through. Its certificates are kept in `state/caddy/`.
- **web** and **api** as locally, with no ports of their own. Behind the password the API answers
  to any host name (`ALLOWED_HOSTS=*`), so a server reached by its IP works too.
- **Simulations** in Docker on the same server, which is why it needs Docker. The API mounts the
  Docker socket to start them ([SECURITY.md](../SECURITY.md)).

## A quick public link from your own machine

For a call, not for lasting use (it lives only while your machine runs): `make cloud-up`, then
`make share` prints an HTTPS link (a Cloudflare quick tunnel) to the password-protected app.

## Checked so far

`make cloud-up` was checked locally (`docker compose config`, `caddy validate`).
