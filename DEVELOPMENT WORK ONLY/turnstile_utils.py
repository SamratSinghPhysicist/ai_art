import requests
import os

# Load secret key (you can override this with a test key in .env)
SECRET_KEY = os.environ.get("TURNSTILE_SECRET_KEY", "0x4AAAAAABkwoedy7D5aGMDfvnp81KbXU6Q")


def verify_turnstile(token: str, ip: str) -> bool:
    """
    Verifies a Cloudflare Turnstile token.
    Automatically bypasses in local dev or when using test site key.
    """
    if not token:
        print("❌ Turnstile verification failed: token missing")
        return False

    # ✅ Automatically bypass in dev environment or with known test tokens
    is_dev_mode = os.environ.get("FLASK_ENV") == "development"
    is_test_token = token.startswith("XXX") or token.startswith("XXXX.DUMMY.TOKEN.XXXX") or "DUMMY" in token

    if is_dev_mode or is_test_token or "00000000000000000000AA" in SECRET_KEY:
        print("🧪 Skipping Turnstile verification (dev/test mode)")
        return True

    try:
        # Real verification request to Cloudflare
        response = requests.post(
            "https://challenges.cloudflare.com/turnstile/v0/siteverify",
            data={
                "secret": SECRET_KEY,
                "response": token,
                "remoteip": ip,
            },
        )
        response.raise_for_status()
        outcome = response.json()
        print("✅ Turnstile verification response:", outcome)
        return outcome.get("success", False)
    except requests.exceptions.RequestException as e:
        print(f"❌ Error verifying Turnstile token: {e}")
        return False
