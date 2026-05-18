import urllib.request
import time
import os

VERSION_URL = "https://raw.githubusercontent.com/subvhome/m59-companion/main/VERSION"
GITHUB_SITE = "https://github.com/subvhome/m59-companion"

def check_for_updates(current_version):
    """
    Checks GitHub for a newer version. 
    Returns (update_available, remote_version)
    """
    print(f"UPDATE: Checking for updates (Current: {current_version})...")
    try:
        # Use a timestamp to bypass GitHub caching
        url = f"{VERSION_URL}?t={int(time.time())}"
        with urllib.request.urlopen(url, timeout=5) as response:
            remote_v = response.read().decode('utf-8').strip()
            
            if float(remote_v) > float(current_version):
                print("\n" + "*"*50)
                print(f" *** NEW VERSION AVAILABLE: v{remote_v} ***")
                print(f" Download the latest build at:")
                print(f" {GITHUB_SITE}")
                print("*"*50 + "\n")
                return True, remote_v
            else:
                print("UPDATE: You are running the latest version.")
                return False, remote_v
    except Exception as e:
        print(f"UPDATE ERROR: Could not reach GitHub: {e}")
        return False, None

if __name__ == "__main__":
    # Test with a fake old version
    check_for_updates("0.10")
