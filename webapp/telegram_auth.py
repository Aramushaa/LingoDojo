import hmac
import hashlib
from urllib.parse import parse_qsl

def verify_telegram_webapp_init_data(init_data: str, bot_token: str) -> dict | None:
    """
    Verifies Telegram Mini App initData signature.
    Returns parsed data dict if valid, else None.

    Telegram docs: check 'hash' using secret = SHA256(bot_token), HMAC-SHA256 over data_check_string.
    """
    if not init_data or not bot_token:
        return None

    # Parse query string into key/value pairs
    pairs = dict(parse_qsl(init_data, keep_blank_values=True))

    received_hash = pairs.pop("hash", None)
    if not received_hash:
        return None

    # Build data_check_string: key=value\n sorted by key
    data_check_string = "\n".join([f"{k}={pairs[k]}" for k in sorted(pairs.keys())])

    # secret_key = SHA256(bot_token)
    secret_key = hashlib.sha256(bot_token.encode("utf-8")).digest()

    # computed_hash = HMAC-SHA256(secret_key, data_check_string)
    computed_hash = hmac.new(secret_key, data_check_string.encode("utf-8"), hashlib.sha256).hexdigest()

    # Timing-safe compare
    if not hmac.compare_digest(computed_hash, received_hash):
        return None

    return pairs
