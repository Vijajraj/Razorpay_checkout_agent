import os
import sys
import time
import urllib.request
import urllib.error
from datetime import datetime

# Default Render Service URL (overridden by RENDER_SERVICE_URL env var or CLI arg)
DEFAULT_URL = "https://razorpay-checkout-agent.onrender.com/api/health"
PING_INTERVAL_SECONDS = 600  # 10 minutes (Render free tier sleeps after 15 minutes)

def ping_service(url: str) -> bool:
    """Send a lightweight GET request to keep Render web service active and prevent cold starts."""
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    try:
        req = urllib.request.Request(
            url,
            headers={"User-Agent": "Render-KeepAlive-Pinger/1.0"}
        )
        with urllib.request.urlopen(req, timeout=20) as response:
            status = response.getcode()
            print(f"[{timestamp}] PING SUCCESS -> {url} (HTTP {status})", flush=True)
            return True
    except urllib.error.HTTPError as e:
        print(f"[{timestamp}] PING HTTP WARNING -> {url} (HTTP {e.code})", flush=True)
        return False
    except Exception as e:
        print(f"[{timestamp}] PING ERROR -> {url} ({e})", flush=True)
        return False

def run_keep_alive_loop(url: str, interval: int = PING_INTERVAL_SECONDS, max_pings: int = None):
    """Run continuous ping loop to keep server awake."""
    print("=" * 65)
    print("RENDER ANTI-COLD-START KEEP-ALIVE PINGER")
    print(f"Target URL : {url}")
    print(f"Interval   : Every {interval // 60} minutes ({interval}s)")
    print("=" * 65)

    count = 0
    # Immediate initial ping
    ping_service(url)
    count += 1

    while max_pings is None or count < max_pings:
        time.sleep(interval)
        ping_service(url)
        count += 1

if __name__ == "__main__":
    target_url = os.getenv("RENDER_SERVICE_URL", DEFAULT_URL)
    if len(sys.argv) > 1:
        target_url = sys.argv[1]
    run_keep_alive_loop(target_url)
