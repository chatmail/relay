import subprocess
import sys
import time
import os
import shutil

# This script automates LXC container creation and relay deployment testing.
# It cleans up old containers, creates a new one, and runs the deployment.

CONTAINER_PREFIX = "testrelay"
CONTAINER_NAME = f"{CONTAINER_PREFIX}-auto"
RELAY_SRC = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))

def run_cmd(cmd, check=True, shell=True):
    print(f"Executing: {cmd}")
    try:
        result = subprocess.run(cmd, shell=shell, check=check, capture_output=True, text=True)
        return result.stdout.strip()
    except subprocess.CalledProcessError as e:
        print(f"Error executing command: {e}")
        print(f"Stdout: {e.stdout}")
        print(f"Stderr: {e.stderr}")
        if check:
            sys.exit(1)
        return None

def cleanup():
    print("--- Cleaning up old containers ---")
    containers = run_cmd("sudo lxc-ls -1").splitlines()
    for c in containers:
        if c.startswith(CONTAINER_PREFIX):
            print(f"Destroying container: {c}")
            run_cmd(f"sudo lxc-destroy -n {c} -f", check=False)

def create_container():
    print(f"--- Creating container: {CONTAINER_NAME} ---")
    run_cmd(f"sudo lxc-create -n {CONTAINER_NAME} -t download -- -d debian -r bookworm -a amd64")

def run_in_container(name, command):
    return run_cmd(f'sudo lxc-attach -n {name} -- bash -c "{command}"')

def prepare_container():
    print("--- Preparing container ---")
    run_cmd(f"sudo lxc-start -n {CONTAINER_NAME}")
    
    # Wait for IP
    print("Waiting for container IP...")
    for _ in range(30):
        ip = run_cmd(f"sudo lxc-info -n {CONTAINER_NAME} -i").split()
        if ip and len(ip) > 1:
            print(f"Container IP: {ip[1]}")
            break
        time.sleep(1)
    else:
        print("Failed to get container IP.")
        sys.exit(1)

    # Disable systemd-resolved to free port 53
    run_in_container(CONTAINER_NAME, "systemctl disable --now systemd-resolved || true")
    run_in_container(CONTAINER_NAME, "echo 'nameserver 8.8.8.8' > /etc/resolv.conf")
    
    # Sync code
    print("Syncing code to container...")
    target_path = f"/var/lib/lxc/{CONTAINER_NAME}/rootfs/relay-ir"
    run_cmd(f"sudo mkdir -p {target_path}")
    run_cmd(f"sudo rsync -av --exclude=.git --exclude='*.log' --exclude='test' {RELAY_SRC}/ {target_path}/")

    # Install dependencies
    print("Installing dependencies inside container...")
    run_in_container(CONTAINER_NAME, "apt-get update && apt-get install -y curl sudo python3-dev gcc")
    run_in_container(CONTAINER_NAME, "apt-get remove --purge -y exim4*")
    run_in_container(CONTAINER_NAME, "curl -LsSf https://astral.sh/uv/install.sh | sh")

def perform_deployment():
    print("--- Running deployment test ---")
    # Using the PATH where uv is installed
    path_env = "export PATH='/root/.local/bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin'"
    deploy_cmd = f"cd /relay-ir && {path_env} && ./scripts/initenv.sh && ./scripts/cmdeploy run --ssh-host @local --skip-dns-check"
    
    try:
        output = run_in_container(CONTAINER_NAME, deploy_cmd)
        print("Deployment Output Summary:")
        print(output[-1000:] if output else "No output") # Show last bit of output
        print("\nSUCCESS: Deployment completed.")
    except Exception:
        print("\nFAILURE: Deployment failed.")
        sys.exit(1)

if __name__ == "__main__":
    if os.geteuid() != 0:
        print("This script must be run as root/sudo.")
        # We don't exit here because the inner run_cmd uses sudo, but it's better to be root.
    
    cleanup()
    create_container()
    prepare_container()
    perform_deployment()
