#!/usr/bin/env bash
# Host Showtime on a Nebius AI Cloud VM (docs/HOSTING.md). Token Factory hosts models, not apps;
# the app runs on a CPU VM with Docker and calls Token Factory and Sandboxes through .env.
#
#   make deploy-nebius                 create the VM if needed, copy the code and .env, start
#   VM_NAME=showtime-2 make deploy-nebius
#
# Needs: the nebius CLI with a profile (nebius profile create), jq, ssh, and an SSH key.
# Copies the committed code (git archive) and .env (mode 600) over SSH; nothing secret is in git.
set -euo pipefail
cd "$(dirname "$0")/.."

VM_NAME="${VM_NAME:-showtime}"
VM_PLATFORM="${VM_PLATFORM:-cpu-d3}"
VM_PRESET="${VM_PRESET:-4vcpu-16gb}"
VM_DISK_GB="${VM_DISK_GB:-50}"
VM_IMAGE_FAMILY="${VM_IMAGE_FAMILY:-ubuntu24.04-driverless}"
VM_USER="${VM_USER:-showtime}"
SSH_KEY="${SSH_KEY:-$HOME/.ssh/id_ed25519}"
APP_DIR="showtime"

die() { echo "error: $*" >&2; exit 1; }
for tool in nebius jq ssh git; do command -v "$tool" >/dev/null || die "$tool is not installed"; done
[ -f .env ] || die ".env is missing"
[ -f "$SSH_KEY.pub" ] || die "no SSH key at $SSH_KEY.pub (ssh-keygen -t ed25519, or set SSH_KEY)"
# the hosted app is public: it must have a password (names checked only, values never printed)
for name in BASIC_AUTH_USER BASIC_AUTH_HASH; do
  grep -q "^$name=." .env || die "$name is not set in .env (make cloud-password gives the hash)"
done

vm_ip() {
  nebius compute instance list --format json |
    jq -r --arg n "$VM_NAME" '.items[]? | select(.metadata.name == $n)
      | .status.network_interfaces[0].public_ip_address.address // empty' | cut -d/ -f1
}

IP="$(vm_ip || true)"
if [ -z "$IP" ]; then
  echo "No VM named $VM_NAME. Create one: $VM_PLATFORM $VM_PRESET, ${VM_DISK_GB} GiB, $VM_IMAGE_FAMILY."
  echo "It is billed per hour while it runs (docs/HOSTING.md has the prices)."
  read -rp "Create it now? [y/N] " ok
  [ "$ok" = "y" ] || die "stopped; nothing was created"
  SUBNET_ID="$(nebius vpc subnet list --format jsonpath='{.items[0].metadata.id}')"
  [ -n "$SUBNET_ID" ] || die "no VPC subnet in this project"
  USER_DATA="$(sed -e "s|__USER__|$VM_USER|" -e "s|__KEY__|$(cat "$SSH_KEY.pub")|" deploy/cloud-init.yaml)"
  nebius compute instance create --name "$VM_NAME" \
    --resources-platform "$VM_PLATFORM" --resources-preset "$VM_PRESET" \
    --boot-disk-managed-disk-name "$VM_NAME-disk" --boot-disk-managed-disk-type network_ssd \
    --boot-disk-managed-disk-size-gibibytes "$VM_DISK_GB" \
    --boot-disk-managed-disk-block-size-bytes 4096 \
    --boot-disk-managed-disk-source-image-family-image-family "$VM_IMAGE_FAMILY" \
    --boot-disk-attach-mode READ_WRITE --cloud-init-user-data "$USER_DATA" \
    --network-interfaces "[{\"name\":\"eth0\",\"subnet_id\":\"$SUBNET_ID\",\"ip_address\":{},\"public_ip_address\":{}}]" \
    >/dev/null
  for _ in $(seq 60); do IP="$(vm_ip || true)"; [ -n "$IP" ] && break; sleep 5; done
  [ -n "$IP" ] || die "the VM has no public address yet; run make deploy-nebius again in a minute"
fi

SSH=(ssh -i "$SSH_KEY" -o StrictHostKeyChecking=accept-new -o ConnectTimeout=10 "$VM_USER@$IP")
echo "Waiting for $IP to finish installing Docker…"
for _ in $(seq 90); do "${SSH[@]}" "test -f /var/lib/cloud/instance/boot-finished && docker info >/dev/null 2>&1" && break; sleep 10; done
"${SSH[@]}" "docker info >/dev/null 2>&1" || die "Docker is not ready on $IP yet; run make deploy-nebius again"

echo "Copying the code and .env…"
git archive --format=tar HEAD |  # run here, it archives this folder only "${SSH[@]}" "mkdir -p $APP_DIR && tar -x -C $APP_DIR"
"${SSH[@]}" "umask 077 && cat > $APP_DIR/.env" < .env
"${SSH[@]}" "cd $APP_DIR && make cloud-up"
SITE="$(grep -E '^SITE_ADDRESS=' .env | cut -d= -f2- || true)"
case "$SITE" in
  ""|:*) echo "Showtime runs at http://$IP" ;;
  *) echo "Showtime runs at https://$SITE once its DNS points at $IP (until then http://$IP)" ;;
esac
