import urllib.request
import time
import os
import sys
import subprocess
import webbrowser

VERSION_URL = "https://raw.githubusercontent.com/subvhome/m59-companion/main/VERSION"
EXE_URL = "https://github.com/subvhome/m59-companion/raw/main/dist/M59Companion.exe"
GITHUB_SITE = "https://github.com/subvhome/m59-companion"

def check_for_updates(current_version):
    """Checks GitHub for a newer version. Returns (update_available, remote_version, release_notes)"""
    try:
        url = f"{VERSION_URL}?t={int(time.time())}"
        with urllib.request.urlopen(url, timeout=5) as response:
            remote_text = response.read().decode('utf-8').strip()
            lines = remote_text.splitlines()
            remote_v = lines[0].strip() if lines else ""
            release_notes = "\n".join(lines[1:]).strip()
            
            def parse(v):
                # Robustly parse version strings like "1.8.0" or "v1.8" into integer lists
                import re
                nums = re.findall(r'\d+', v)
                return [int(n) for n in nums] if nums else [0]
                
            return (parse(remote_v) > parse(current_version)), remote_v, release_notes
    except:
        return False, None, None

def download_update():
    """Downloads the latest exe to a temporary file."""
    temp_path = "M59Companion_new.exe"
    try:
        urllib.request.urlretrieve(EXE_URL, temp_path)
        return temp_path if os.path.exists(temp_path) else None
    except:
        return None

def apply_update(new_exe_path):
    """Uses PowerShell to swap files silently after app exit."""
    current_exe = sys.executable
    # PowerShell Script: Wait 5s (to prevent MEI cleanup race), Swap, Alert, Restart
    ps_script = f"""
    Start-Sleep -s 5
    if (Test-Path '{new_exe_path}') {{
        Move-Item -Path '{new_exe_path}' -Destination '{current_exe}' -Force
        [System.Reflection.Assembly]::LoadWithPartialName('System.Windows.Forms') | Out-Null
        [System.Windows.Forms.MessageBox]::Show('M59 Companion has been updated to the latest version.', 'Update Complete')
        Start-Process '{current_exe}'
    }}
    """
    subprocess.Popen(["powershell.exe", "-NoProfile", "-WindowStyle", "Hidden", "-Command", ps_script], 
                     creationflags=subprocess.CREATE_NO_WINDOW)
    sys.exit()

def open_browser():
    webbrowser.open(GITHUB_SITE)

if __name__ == "__main__":
    # Test with a fake old version
    check_for_updates("0.10")
