"""
Response masking for sensitive gateway responses.

Rules:
- hCaptcha / Checkpoint / Captcha responses: NEVER show the real captcha message.
  50% → random fake display from _FAKE_POOL
  50% → "Declined" (clean generic, no captcha mention)

- 3DS / requires_action responses:
  50% → random fake display from _FAKE_POOL
  50% → exact original 3DS response
"""

import random

_CAPTCHA_KEYWORDS = [
    "captcha", "hcaptcha", "h-captcha",
    "checkpoint denied", "checkpoint",
    "captcha solving failed", "captcha detected",
    "captcha blocked",
]

_THREED_KEYWORDS = [
    "3ds", "3d secure", "3d_secure", "requires_action",
    "3ds required", "3d_auth", "3ds_authentication",
    "3d_authentication", "three_d_secure",
    "authentication_required",
]

_FAKE_POOL = [
    "Generic Declined - 3DS Bypassed",
    "3DS Bypassed - Generic Decline",
    "Declined - Fraudulent",
    "Declined - Payment Failed",
    "Generic Decline",
    "Declined - 3DS Bypassed",
    "Payment Failed - Generic Decline",
    "Fraudulent - Declined",
]


def _pick_fake() -> str:
    return random.choice(_FAKE_POOL)


def _is_captcha(response: str) -> bool:
    rl = response.lower()
    return any(k in rl for k in _CAPTCHA_KEYWORDS)


def _is_3ds(response: str) -> bool:
    rl = response.lower()
    return any(k in rl for k in _THREED_KEYWORDS)


def mask_response(response: str) -> str:
    """
    Apply 50/50 masking to captcha and 3DS responses.
    Never returns the raw captcha message.
    """
    if not response:
        return response

    if _is_captcha(response):
        if random.random() < 0.5:
            return _pick_fake()
        else:
            return "Declined"

    if _is_3ds(response):
        if random.random() < 0.5:
            return _pick_fake()
        else:
            return response

    return response


def mask_status(response: str, original_status: str) -> str:
    """
    Return the appropriate status after masking.
    Captcha/3DS masked responses are treated as DECLINED.
    """
    masked = mask_response(response)
    if masked != response:
        return "DECLINED"
    return original_status
