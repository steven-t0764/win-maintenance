<p align="center">
  <img src="assets/terminal.svg" alt="Animated command prompt running Weekly_Maintenance.py" width="820">
</p>

# Windows Weekly Maintenance

A Python script that handles routine Windows upkeep in one run:

- **Closes open apps** so their temp files can be cleaned (with a protected list it never touches)
- Clears old files out of the user and system **temp folders**
- Checks for **Windows, Microsoft product and driver updates**
- **Installs Windows and driver updates**
- Lists any **devices reporting driver errors** in Device Manager
- **Restarts the PC** when finished, after a countdown you can cancel
- Writes everything to a **log file** so you can see what happened

Everything lives in a single file: [`Weekly_Maintenance.py`](Weekly_Maintenance.py).

> [!WARNING]
> With the default settings the script **closes your open apps and force-closes any that don't respond — unsaved work is lost** — and then **restarts the computer**. Save everything before it runs, or schedule it for a time you're away. Set `DRY_RUN = True` to try it safely first.

---

## Requirements

| Requirement | Why |
|---|---|
| Windows 10 / 11 | The script calls Windows-only PowerShell commands |
| Python 3.8+ | Uses only the standard library — no `pip install` needed |
| [PSWindowsUpdate](https://www.powershellgallery.com/packages/PSWindowsUpdate) PowerShell module | Provides `Get-WindowsUpdate`, `Install-WindowsUpdate` and `Get-WURebootStatus` |
| Administrator rights | Needed to clean `C:\Windows\Temp`, install updates and restart |

Install the PowerShell module once, from an **admin** PowerShell window:

```powershell
Install-Module PSWindowsUpdate -Scope AllUsers -Force
```

---

## How the script is built

The script is a settings block, a few helpers, one function per task, and a main section that runs them in order.

### 1. Settings

All behaviour is controlled by the constants at the top of the file, so you never have to touch the logic:

```python
DRY_RUN = False                 # True = only report what would happen
INSTALL_UPDATES = True          # True = install updates. False = only report them
SKIP_DRIVERS_ON_INSTALL = False # False = install driver updates too
CLOSE_APPS = True               # close open apps before cleaning temp files
FORCE_CLOSE = True              # kill apps that won't close (UNSAVED WORK IS LOST)
CLOSE_WAIT_SECONDS = 45         # how long apps get to close on their own
RESTART_AFTER = True            # restart the computer when everything is done
RESTART_DELAY_SECONDS = 120     # countdown before restart
MAX_AGE_DAYS = 7                # only delete temp items older than this
LOG_FILE = Path.home() / "weekly_maintenance.log"
```

`DRY_RUN = True` turns the whole script into a report: nothing is closed, deleted, installed or restarted — the log just says what *would* happen.

`PROTECTED_APPS` lists processes that are never closed — Explorer, the Start menu, Settings, and every terminal (`cmd`, `powershell`, `pwsh`, Windows Terminal) so the script doesn't close the window it's running in. Add to this list for anything you never want closed.

### 2. Helpers

- **`log(msg)`** — prints a timestamped line and appends it to `weekly_maintenance.log` in your user folder.
- **`run_powershell(command)`** — runs a PowerShell command with `subprocess.run` (`-NoProfile` for a clean, fast start) and returns `(exit_code, stdout, stderr)`. Every app, update and device step goes through this one function.
- **`get_size(item)`** — size of a file, or the total of everything inside a folder.

### 3. Closing apps — `close_apps()`

1. `open_apps_filter()` builds a PowerShell filter for processes that have a visible window, skipping `PROTECTED_APPS`, any Python process and the script's own process ID.
2. It asks each app to close politely with `CloseMainWindow()` — the same as clicking ✕, so apps can prompt to save.
3. It waits `CLOSE_WAIT_SECONDS`.
4. Anything still open is force-closed with `Stop-Process -Force` when `FORCE_CLOSE = True`, or just logged when it's `False`.

Closing apps first frees up temp files they were holding, so the cleanup removes more.

### 4. Temp folder cleanup — `clean_temp(folder)`

1. Works out a cutoff time from `MAX_AGE_DAYS` (default 7 days).
2. Loops over each top-level item in the folder and skips anything modified more recently than the cutoff.
3. Measures it with `get_size()`, then removes folders with `shutil.rmtree` and files with `unlink`.
4. Locked or protected files raise `PermissionError`/`OSError` and are counted as **skipped** instead of crashing the script.
5. Logs a summary: MB freed, items removed, items skipped.

### 5. Update checks — `check_updates()` and `check_driver_updates()`

```powershell
Get-WindowsUpdate -MicrosoftUpdate                    # Windows + Office etc.
Get-WindowsUpdate -MicrosoftUpdate -UpdateType Driver # drivers only
```

`-MicrosoftUpdate` widens the search beyond Windows itself to other Microsoft products. Feature upgrades (new Windows versions) don't appear here, so the script logs a reminder to check **Settings › Windows Update** for those.

### 6. Installing updates — `install_updates()`

Installs Windows, Microsoft product **and driver** updates:

```powershell
Install-WindowsUpdate -MicrosoftUpdate -AcceptAll -IgnoreReboot
```

- `-AcceptAll` — no interactive prompts
- `-IgnoreReboot` — Windows Update never restarts on its own; the script's own restart step handles that at the end
- Set `SKIP_DRIVERS_ON_INSTALL = True` to add `-NotCategory 'Drivers'` and only report driver updates instead

Afterwards it calls `Get-WURebootStatus -Silent` and logs whether updates need a restart.

> **Heads-up:** drivers from Windows Update can be generic or older than the manufacturer's (graphics cards especially). If an update breaks Wi-Fi, audio or display, roll it back in **Device Manager › Properties › Driver › Roll Back Driver**, then set `SKIP_DRIVERS_ON_INSTALL = True` or install that driver from the manufacturer's site.

### 7. Problem devices — `check_problem_devices()`

```powershell
Get-PnpDevice -PresentOnly | Where-Object Status -eq 'Error'
```

Lists any connected hardware Windows flags with an error — usually a sign of a missing or broken driver.

### 8. Restart — `restart_computer()`

```
shutdown /r /t 120 /c "Weekly maintenance restart"
```

Windows shows a countdown notice. **To cancel, run `shutdown /a`** in any Command Prompt before it reaches zero.

### 9. Main run order

```
start log → close apps → clean temp folders → check updates → check drivers
          → install updates → check problem devices → done → restart
```

---

## Usage

1. Save your work and close anything important.
2. Open **Command Prompt or PowerShell as Administrator**.
3. Run it:

   ```
   python Weekly_Maintenance.py
   ```

4. Check `%USERPROFILE%\weekly_maintenance.log` after the restart.

**First time?** Set `DRY_RUN = True`, run it, read the log, then set it back to `False`.

### Recommended settings

| Goal | Settings |
|---|---|
| Just see what would happen | `DRY_RUN = True` |
| Full weekly run (default) | `DRY_RUN = False`, everything else as shipped |
| Run while you're still working | `CLOSE_APPS = False`, `RESTART_AFTER = False` |
| Never lose unsaved work | `FORCE_CLOSE = False` |
| Updates without drivers | `SKIP_DRIVERS_ON_INSTALL = True` |

---

## Running it weekly (Task Scheduler)

1. Open **Task Scheduler** › **Create Task…**
2. **General:** name it `Weekly Maintenance`, tick **Run with highest privileges**.
3. **Triggers:** New › Weekly › pick a day and a time you're usually away from the PC.
4. **Actions:** New › Start a program
   - Program: `python` (or the full path to `python.exe`)
   - Arguments: `"C:\Scripts\Weekly_Maintenance.py"`
5. Click **OK**. Check the log after the first scheduled run.

---

## Log output example

```
[2026-11-04 09:00:00] === Weekly maintenance started (DRY_RUN=False, INSTALL_UPDATES=True, CLOSE_APPS=True, RESTART_AFTER=True) ===
[2026-11-04 09:00:01] Closing apps politely: chrome, Discord, Spotify
[2026-11-04 09:00:46] All apps closed.
[2026-11-04 09:00:47] C:\Users\you\AppData\Local\Temp: freed 412.3 MB across 87 items, skipped 4 locked items
[2026-11-04 09:00:52] Checking for Windows updates (including Microsoft products)...
...
[2026-11-04 09:12:10] === Done ===
[2026-11-04 09:12:10] Restarting in 120 seconds. To cancel, run: shutdown /a
```
