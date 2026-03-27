import subprocess

def run_nmap_scan(target: str):
    command = [
        "nmap",
        "-sT",                  # TCP connect scan (works in Docker)
        "-p", "1-1000",         # scan more ports
        "--host-timeout", "30s",
        "-oX", "-",
        target
    ]

    result = subprocess.run(
        command,
        capture_output=True,
        text=True,
        timeout=60
    )

    if result.returncode != 0:
        raise Exception(f"Nmap failed: {result.stderr}")

    return result.stdout