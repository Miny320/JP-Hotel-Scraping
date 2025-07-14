import pytz
from datetime import datetime
import hashlib
import re
from .config import tz, TIMEZONE

def get_last_updated_at() -> str:
    """Get the current time in the configured timezone as a string."""
    return datetime.now(tz).strftime("%Y-%m-%d %H:%M:%S")

def get_process_hash_id() -> str:
    """Get a hash ID for the current process based on timezone."""
    return hashlib.md5(TIMEZONE.encode()).hexdigest()

def to_e164_jp_phone(phone: str) -> str:
    """Convert a Japanese phone number to E.164 format."""
    if not phone:
        return phone
    digits = re.sub(r'\D', '', phone)
    if digits.startswith('0'):
        digits = digits[1:]
    return '+81' + digits 

