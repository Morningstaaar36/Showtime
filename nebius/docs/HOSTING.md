# Hosting Showtime on Nebius

**Can it run on Token Factory itself? No.** Token Factory hosts models (serverless models,
dedicated endpoints, custom weights), not web apps
([docs index](https://docs.tokenfactory.nebius.com/llms.txt)). Showtime already *uses* Token
Factory for every AI call (`LLM_PROVIDER=nebius`) and Nebius Sandboxes for every simulation
(`SANDBOX_PROVIDER=nebius`); the app itself runs on a small **Nebius AI Cloud** VM with Docker.

## What you need

- A Nebius AI Cloud account and the `nebius` CLI:
  `curl -sSL https://artifacts.nebius.cloud/cli/install.sh | bash`, then `nebius profile create`
  ([CLI](https://docs.nebius.com/cli/install.md)).
- An SSH key (`ssh-keygen -t ed25519`), `jq` and `git`.
- Your `.env`, working locally (keys for Token Factory, Sandboxes and Tavily).

## Three steps

1. **Set a password and the address** in `.env` (the hosted app is public; the password keeps
   strangers from spending your model credit):

   ```bash
   make cloud-password            # asks for a password, prints its hash
   ```

   ```dotenv
   BASIC_AUTH_USER=organizer
   BASIC_AUTH_HASH=<the hash>
   SITE_ADDRESS=:80                               # or your domain, e.g. showtime.example.org (HTTPS)
   WEB_ORIGIN=http://<the VM's address>           # or https://showtime.example.org
   ```

2. **Commit your changes** (the VM gets the committed code; `.env` is copied separately and
   never enters git).

3. **Deploy:**

   ```bash
   make deploy-nebius
   ```

   It finds the VM named `showtime`, or asks before creating one (CPU `cpu-d3`, `4vcpu-16gb`,
   50 GiB SSD, Ubuntu 24.04; cloud-init installs Docker), copies the code and `.env` (mode 600)
   over SSH, builds the images and starts the stack behind Caddy. It prints the address.

Run it again after every change: it copies the new code and restarts. Change the size with
`VM_PRESET=2vcpu-8gb make deploy-nebius` (enough when `SANDBOX_PROVIDER=nebius` runs the
simulations), or the name with `VM_NAME=...`.

## What runs on the VM

`make cloud-up` (`docker-compose.yml` + `docker-compose.cloud.yml`):

- **Caddy** on ports 80 and 443: the only open ports. With a domain in `SITE_ADDRESS` it gets an
  HTTPS certificate on its own (point the domain's DNS at the VM first). It asks for the password
  on every page and every API call, and streams live test progress through.
- **web** and **api** as locally, with no ports of their own.
- **Simulations**: in Nebius Sandboxes with `SANDBOX_PROVIDER=nebius`, or in Docker on the VM
  (the default), which is why the VM has Docker.

## Costs

Compute is billed per hour while the VM runs: $0.015 per vCPU-hour and $0.0045 per GiB-hour
from 2026-10-01 ([pricing](https://docs.nebius.com/compute/resources/pricing.md)), so about
$0.13/h for `4vcpu-16gb` or $0.07/h for `2vcpu-8gb`, plus the disk. Stop it when you don't need
it: `nebius compute instance stop --id <id>`; `make cloud-down` on the VM stops the app only.

## Other ways

- **Serverless AI endpoint** (`nebius ai endpoint create --image ... --container-port 80`,
  [docs](https://docs.nebius.com/serverless/endpoints/manage.md)): a managed HTTPS address for one
  container. Showtime runs two (api, web) plus simulations, and keeps its database on disk, so it
  would need one combined image, a volume and `SANDBOX_PROVIDER=nebius`. The VM is simpler.
- **Any other server with Docker**: copy the folder and `.env`, then `make cloud-up`.

## Not verified

No Nebius account was available while this was written (sign-up does not list Bangladesh), so
`make deploy-nebius` has not created a VM yet. The CLI flags come from the Nebius Compute
[quickstart](https://docs.nebius.com/compute/quickstart.md); `make cloud-up` was checked locally
(`docker compose config`, `caddy validate`).
