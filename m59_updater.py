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
    """Checks GitHub for a newer version. Returns (update_available, remote_version)"""
    try:
        url = f"{VERSION_URL}?t={int(time.time())}"
        with urllib.request.urlopen(url, timeout=5) as response:
            remote_v = response.read().decode('utf-8').strip()
            
            def parse(v):
                # Robustly parse version strings like "1.8.0" or "v1.8" into integer lists
                import re
                nums = re.findall(r'\d+', v)
                return [int(n) for n in nums] if nums else [0]
                
            return (parse(remote_v) > parse(current_version)), remote_v
    except:
        return False, None

def download_update(progress_callback=None):
    """Downloads the latest exe to a temporary file with progress tracking."""
    temp_path = "M59Companion_new.exe"
    
    def reporthook(block_num, block_size, total_size):
        if progress_callback and total_size > 0:
            downloaded = block_num * block_size
            percent = (downloaded / total_size) * 100
            progress_callback(min(100.0, percent))
            
    try:
        if progress_callback:
            urllib.request.urlretrieve(EXE_URL, temp_path, reporthook=reporthook)
        else:
            urllib.request.urlretrieve(EXE_URL, temp_path)
        return temp_path if os.path.exists(temp_path) else None
    except:
        return None

def apply_update(new_exe_path):
    """Uses PowerShell to safely swap files by renaming the current running exe."""
    current_exe = sys.executable
    old_exe = current_exe + ".old"
    current_pid = os.getpid()
    
    # PowerShell Script: Wait for process to exit, Rename old, Move new, Alert, Restart
    ps_script = f"""
    Wait-Process -Id {current_pid} -ErrorAction SilentlyContinue
    Start-Sleep -s 1
    if (Test-Path '{new_exe_path}') {{
        if (Test-Path '{old_exe}') {{ Remove-Item -Path '{old_exe}' -Force }}
        Rename-Item -Path '{current_exe}' -NewName '{os.path.basename(old_exe)}' -Force
        Move-Item -Path '{new_exe_path}' -Destination '{current_exe}' -Force
        [System.Reflection.Assembly]::LoadWithPartialName('System.Windows.Forms') | Out-Null
        [System.Windows.Forms.MessageBox]::Show('M59 Companion has been updated to the latest version.', 'Update Complete')
        Start-Process '{current_exe}'
    }}
    """
    subprocess.Popen(["powershell.exe", "-NoProfile", "-WindowStyle", "Hidden", "-Command", ps_script], 
                     creationflags=subprocess.CREATE_NO_WINDOW)

def open_browser():
    webbrowser.open(GITHUB_SITE)

if __name__ == "__main__":
    # Test with a fake old version
    check_for_updates("0.10")
