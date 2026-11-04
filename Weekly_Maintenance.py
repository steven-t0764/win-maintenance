import shutil
import subprocess
import tempfile
import time
from datetime import datetime
from pathlib import Path

# ---------- SETTINGS ----------
DRY_RUN = True            # True = only list what would be deleted. False = really delete.
INSTALL_UPDATES = True   # True = actually install updates. False = only report them.
SKIP_DRIVERS_ON_INSTALL = False  # False = install driver updates too. True = leave drivers out
MAX_AGE_DAYS = 0          # only delete items older than this
LOG_FILE = Path.home() / "weekly_maintenance.log"

TEMP_DIRS = [
    Path(tempfile.gettempdir()),   # user temp
    Path(r"C:\Windows\Temp"),      # system temp (needs admin)
]
# ------------------------------


def log(msg):
    line = f"[{datetime.now():%Y-%m-%d %H:%M:%S}] {msg}"
    print(line)
    with open(LOG_FILE, "a", encoding="utf-8") as f:
        f.write(line + "\n")


def run_powershell(command):
    """Run a PowerShell command and return (exit_code, stdout, stderr)."""
    result = subprocess.run(
        ["powershell", "-NoProfile", "-Command", command],
        capture_output=True, text=True,
    )
    return result.returncode, result.stdout.strip(), result.stderr.strip()


def get_size(item):
    """Size in bytes. Files: their size. Folders: sum of everything inside."""
    try:
        if item.is_file():
            return item.stat().st_size
        return sum(f.stat().st_size for f in item.rglob("*") if f.is_file())
    except OSError:
        return 0


def clean_temp(folder):
    cutoff = time.time() - (MAX_AGE_DAYS * 24 * 60 * 60)
    freed = 0
    skipped = 0
    count = 0

    if not folder.exists():
        log(f"Skipping {folder} (not found)")
        return

    for item in folder.iterdir():
        try:
            if item.stat().st_mtime > cutoff:    # newer than cutoff -> leave it
                continue
            size = get_size(item)
            if DRY_RUN:
                log(f"  [dry run] would delete: {item}")
            elif item.is_dir():
                shutil.rmtree(item)
            else:
                item.unlink()
            freed += size
            count += 1
        except (PermissionError, OSError):
            skipped += 1                          # in use or protected

    verb = "would free" if DRY_RUN else "freed"
    log(f"{folder}: {verb} {freed / 1_048_576:.1f} MB across {count} items, "
        f"skipped {skipped} locked items")


def check_updates():
    log("Checking for Windows updates (including Microsoft products)...")
    code, out, err = run_powershell("Get-WindowsUpdate -MicrosoftUpdate")
    if code != 0:
        log(f"Update check failed: {err}")
    elif out:
        log("Updates available:\n" + out)
    else:
        log("No updates available.")
    log("Reminder: feature upgrades (like 26H2) only show in Settings > Windows Update.")


def check_driver_updates():
    log("Checking for driver updates...")
    code, out, err = run_powershell("Get-WindowsUpdate -MicrosoftUpdate -UpdateType Driver")
    if code != 0:
        log(f"Driver update check failed: {err}")
    elif out:
        log("Driver updates available:\n" + out)
    else:
        log("No driver updates available.")


def install_updates():
    if not INSTALL_UPDATES:
        log("Update install is OFF (INSTALL_UPDATES = False). Skipping.")
        return

    scope = "Windows updates only, drivers skipped" if SKIP_DRIVERS_ON_INSTALL else "Windows + driver updates"
    log(f"Installing {scope} (this can take a while)...")
    command = "Install-WindowsUpdate -MicrosoftUpdate -AcceptAll -IgnoreReboot"
    if SKIP_DRIVERS_ON_INSTALL:
        command += " -NotCategory 'Drivers'"

    code, out, err = run_powershell(command)
    if code != 0:
        log(f"Install failed: {err}")
    else:
        log("Install finished:\n" + (out or "(no output)"))

    code, out, err = run_powershell("Get-WURebootStatus -Silent")
    if out.strip().lower() == "true":
        log("RESTART REQUIRED to finish updates. Restart when convenient.")
    else:
        log("No restart required.")


def check_problem_devices():
    log("Checking for devices with driver problems...")
    cmd = (
        "Get-PnpDevice -PresentOnly | Where-Object Status -eq 'Error' | "
        "Select-Object FriendlyName, Class, Status | Format-Table -AutoSize | "
        "Out-String -Width 200"
    )
    code, out, err = run_powershell(cmd)
    if code != 0:
        log(f"Device check failed: {err}")
    elif out:
        log("Devices reporting errors (may need a driver):\n" + out)
    else:
        log("No devices reporting driver problems.")


if __name__ == "__main__":
    log(f"=== Weekly maintenance started "
        f"(DRY_RUN={DRY_RUN}, INSTALL_UPDATES={INSTALL_UPDATES}) ===")
    for d in TEMP_DIRS:
        clean_temp(d)
    check_updates()
    check_driver_updates()
    install_updates()
    check_problem_devices()
    log("=== Done ===")