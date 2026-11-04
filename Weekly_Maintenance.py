import os
import shutil
import subprocess
import tempfile
import time
from datetime import datetime
from pathlib import Path

# ---------- SETTINGS ----------
DRY_RUN = False            # True = only report what would happen. False = really do it.
INSTALL_UPDATES = True   # True = install updates. False = only report them.
SKIP_DRIVERS_ON_INSTALL = False   # False = install driver updates too. True = leave drivers out
CLOSE_APPS = True        # True = close open apps before cleaning temp files
FORCE_CLOSE = True       # True = kill apps that won't close (UNSAVED WORK IS LOST)
CLOSE_WAIT_SECONDS = 45   # how long to let apps close on their own
RESTART_AFTER = True     # True = restart the computer when everything is done
RESTART_DELAY_SECONDS = 120   # countdown before restart. Cancel with: shutdown /a
MAX_AGE_DAYS = 7          # only delete items older than this
LOG_FILE = Path.home() / "weekly_maintenance.log"

TEMP_DIRS = [
    Path(tempfile.gettempdir()),   # user temp
    Path(r"C:\Windows\Temp"),      # system temp (needs admin)
]

# Apps that must never be closed (the script runs inside some of these)
PROTECTED_APPS = [
    "explorer", "powershell", "pwsh", "cmd", "conhost", "WindowsTerminal",
    "OpenConsole", "ApplicationFrameHost", "TextInputHost", "SystemSettings",
    "ShellExperienceHost", "StartMenuExperienceHost", "SearchHost", "LockApp",
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


def open_apps_filter():
    """PowerShell snippet that selects apps with a visible window, minus protected ones."""
    protected = ",".join(f"'{name}'" for name in PROTECTED_APPS)
    return (
        f"$skip = @({protected}); "
        "Get-Process | Where-Object { $_.MainWindowHandle -ne 0 "
        f"-and $_.Id -ne {os.getpid()} "
        "-and $_.ProcessName -notlike 'python*' "
        "-and $skip -notcontains $_.ProcessName }"
    )


def list_open_apps():
    code, out, err = run_powershell(
        open_apps_filter() + " | Select-Object -ExpandProperty ProcessName | Sort-Object -Unique"
    )
    return out.splitlines() if code == 0 and out else []


def close_apps():
    if not CLOSE_APPS:
        log("Close apps is OFF (CLOSE_APPS = False). Skipping.")
        return

    apps = list_open_apps()
    if not apps:
        log("No open apps to close.")
        return

    if DRY_RUN:
        log(f"[dry run] would close: {', '.join(apps)}")
        return

    log(f"Closing apps politely: {', '.join(apps)}")
    run_powershell(open_apps_filter() + " | ForEach-Object { $_.CloseMainWindow() | Out-Null }")
    time.sleep(CLOSE_WAIT_SECONDS)

    remaining = list_open_apps()
    if not remaining:
        log("All apps closed.")
    elif FORCE_CLOSE:
        log(f"Force-closing apps that did not close: {', '.join(remaining)}")
        run_powershell(open_apps_filter() + " | Stop-Process -Force")
        time.sleep(3)
    else:
        log(f"Still open (FORCE_CLOSE is off): {', '.join(remaining)}")


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
    if DRY_RUN:
        log("[dry run] would install updates. Skipping.")
        return

    log("Installing updates (this can take a while)...")
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
        log("RESTART REQUIRED to finish updates.")
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


def restart_computer():
    if not RESTART_AFTER:
        log("Restart is OFF (RESTART_AFTER = False). Skipping.")
        return
    if DRY_RUN:
        log(f"[dry run] would restart in {RESTART_DELAY_SECONDS} seconds")
        return
    log(f"Restarting in {RESTART_DELAY_SECONDS} seconds. To cancel, run: shutdown /a")
    subprocess.run(["shutdown", "/r", "/t", str(RESTART_DELAY_SECONDS),
                    "/c", "Weekly maintenance restart"])


if __name__ == "__main__":
    log(f"=== Weekly maintenance started (DRY_RUN={DRY_RUN}, "
        f"INSTALL_UPDATES={INSTALL_UPDATES}, CLOSE_APPS={CLOSE_APPS}, "
        f"RESTART_AFTER={RESTART_AFTER}) ===")
    close_apps()
    for d in TEMP_DIRS:
        clean_temp(d)
    check_updates()
    check_driver_updates()
    install_updates()
    check_problem_devices()
    log("=== Done ===")
    restart_computer()