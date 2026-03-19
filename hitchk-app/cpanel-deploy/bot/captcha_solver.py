import aiohttp
import asyncio
import os
import re
import json
import logging
from urllib.parse import urlparse, urljoin

logger = logging.getLogger(__name__)

CAPTCHAAI_KEY = os.environ.get("CAPTCHAAI_API_KEY", "")
CAPTCHAAI_IN = "https://ocr.captchaai.com/in.php"
CAPTCHAAI_RES = "https://ocr.captchaai.com/res.php"

MAX_POLL_ATTEMPTS = 40
POLL_INTERVAL = 5

UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"


async def solve_turnstile(sitekey, pageurl, session=None, action=None, cdata=None):
    if not CAPTCHAAI_KEY:
        logger.warning("CAPTCHAAI_API_KEY not set")
        return None
    own_session = session is None
    if own_session:
        session = aiohttp.ClientSession()
    try:
        submit_data = {
            "key": CAPTCHAAI_KEY,
            "method": "turnstile",
            "sitekey": sitekey,
            "pageurl": pageurl,
            "json": "1",
        }
        if action:
            submit_data["action"] = action
        if cdata:
            submit_data["data"] = cdata
        logger.info(f"Submitting Turnstile solve: sitekey={sitekey[:20]}... url={pageurl[:60]} action={action} cdata={cdata is not None}")
        async with session.post(CAPTCHAAI_IN, data=submit_data) as resp:
            result = await resp.json(content_type=None)
            if result.get("status") != 1:
                logger.warning(f"CaptchaAI submit failed: {result}")
                return None
            task_id = result["request"]
            logger.info(f"CaptchaAI task created: {task_id}")

        await asyncio.sleep(10)

        for attempt in range(MAX_POLL_ATTEMPTS):
            params = {
                "key": CAPTCHAAI_KEY,
                "action": "get",
                "id": task_id,
                "json": "1",
            }
            async with session.get(CAPTCHAAI_RES, params=params) as resp:
                result = await resp.json(content_type=None)
                if result.get("status") == 1:
                    token = result["request"]
                    logger.info(f"CaptchaAI solved! Token: {token[:30]}...")
                    return token
                if result.get("request") != "CAPCHA_NOT_READY":
                    logger.warning(f"CaptchaAI error: {result}")
                    return None
            await asyncio.sleep(POLL_INTERVAL)

        logger.warning("CaptchaAI timeout - max poll attempts reached")
        return None
    except Exception as e:
        logger.error(f"CaptchaAI solve_turnstile error: {e}")
        return None
    finally:
        if own_session:
            await session.close()


async def solve_hcaptcha(sitekey, pageurl, session=None):
    if not CAPTCHAAI_KEY:
        logger.warning("CAPTCHAAI_API_KEY not set")
        return None
    own_session = session is None
    if own_session:
        session = aiohttp.ClientSession()
    try:
        submit_data = {
            "key": CAPTCHAAI_KEY,
            "method": "hcaptcha",
            "sitekey": sitekey,
            "pageurl": pageurl,
            "json": "1",
        }
        logger.info(f"Submitting hCaptcha solve: sitekey={sitekey[:20]}... url={pageurl[:60]}")
        async with session.post(CAPTCHAAI_IN, data=submit_data) as resp:
            result = await resp.json(content_type=None)
            if result.get("status") != 1:
                logger.warning(f"CaptchaAI hcaptcha submit failed: {result}")
                return None
            task_id = result["request"]
            logger.info(f"CaptchaAI hcaptcha task created: {task_id}")

        await asyncio.sleep(10)

        for attempt in range(MAX_POLL_ATTEMPTS):
            params = {
                "key": CAPTCHAAI_KEY,
                "action": "get",
                "id": task_id,
                "json": "1",
            }
            async with session.get(CAPTCHAAI_RES, params=params) as resp:
                result = await resp.json(content_type=None)
                if result.get("status") == 1:
                    token = result["request"]
                    logger.info(f"CaptchaAI hcaptcha solved! Token: {token[:30]}...")
                    return token
                if result.get("request") != "CAPCHA_NOT_READY":
                    logger.warning(f"CaptchaAI hcaptcha error: {result}")
                    return None
            await asyncio.sleep(POLL_INTERVAL)

        logger.warning("CaptchaAI hcaptcha timeout")
        return None
    except Exception as e:
        logger.error(f"CaptchaAI solve_hcaptcha error: {e}")
        return None
    finally:
        if own_session:
            await session.close()


def _extract_turnstile_params(html):
    params = {'sitekey': None, 'action': None, 'cdata': None}

    sitekey_patterns = [
        r'class=["\'][^"\']*cf-turnstile[^"\']*["\'][^>]*data-sitekey=["\']([^"\']+)["\']',
        r'data-sitekey=["\']([^"\']+)["\'][^>]*class=["\'][^"\']*cf-turnstile',
        r'challenges\.cloudflare\.com/turnstile[^"\']*sitekey=([^&"\'&amp;]+)',
        r'data-sitekey=["\']([0-9a-zA-Z_x-]+)["\']',
        r'sitekey[\s"\'=:]+["\']?(0x[0-9a-zA-Z_-]+)',
        r'"sitekey"\s*:\s*"([^"]+)"',
        r"'sitekey'\s*:\s*'([^']+)'",
        r'siteKey["\s:=]+["\']([^"\']+)["\']',
    ]
    for pat in sitekey_patterns:
        m = re.search(pat, html, re.IGNORECASE | re.DOTALL)
        if m and len(m.group(1)) > 10:
            params['sitekey'] = m.group(1)
            break

    turnstile_block = re.search(r'(<[^>]*cf-turnstile[^>]*>)', html, re.IGNORECASE | re.DOTALL)
    if turnstile_block:
        block = turnstile_block.group(1)

        action_m = re.search(r'data-action=["\']([^"\']+)["\']', block, re.IGNORECASE)
        if action_m:
            params['action'] = action_m.group(1)

        cdata_m = re.search(r'data-cdata=["\']([^"\']+)["\']', block, re.IGNORECASE)
        if cdata_m:
            params['cdata'] = cdata_m.group(1)

    if not params['action']:
        action_m = re.search(r'data-action=["\']([^"\']+)["\']', html, re.IGNORECASE)
        if action_m:
            params['action'] = action_m.group(1)
    if not params['cdata']:
        cdata_m = re.search(r'data-cdata=["\']([^"\']+)["\']', html, re.IGNORECASE)
        if cdata_m:
            params['cdata'] = cdata_m.group(1)

    js_action = re.search(r'["\']action["\']\s*:\s*["\']([^"\']+)["\']', html)
    if js_action and not params['action']:
        params['action'] = js_action.group(1)
    js_cdata = re.search(r'["\']cData["\']\s*:\s*["\']([^"\']+)["\']', html)
    if js_cdata and not params['cdata']:
        params['cdata'] = js_cdata.group(1)

    return params


def _detect_captcha_type(html):
    html_lower = html.lower()
    if 'cf-turnstile' in html_lower or 'challenges.cloudflare.com/turnstile' in html_lower:
        return 'turnstile'
    if 'hcaptcha' in html_lower or 'h-captcha' in html_lower:
        return 'hcaptcha'
    if 'turnstile' in html_lower:
        return 'turnstile'
    if 'recaptcha' in html_lower or 'g-recaptcha' in html_lower:
        return 'turnstile'
    return 'turnstile'


def _extract_form_data(html):
    data = {}

    auth_patterns = [
        r'name=["\']authenticity_token["\'][^>]*value=["\']([^"\']+)["\']',
        r'value=["\']([^"\']+)["\'][^>]*name=["\']authenticity_token["\']',
        r'"authenticity_token"\s*:\s*"([^"]+)"',
    ]
    for pat in auth_patterns:
        m = re.search(pat, html, re.IGNORECASE)
        if m:
            data['authenticity_token'] = m.group(1)
            break

    hidden_inputs = re.findall(
        r'<input[^>]+type=["\']hidden["\'][^>]*name=["\']([^"\']+)["\'][^>]*value=["\']([^"\']*)["\']',
        html, re.IGNORECASE
    )
    hidden_inputs2 = re.findall(
        r'<input[^>]*name=["\']([^"\']+)["\'][^>]*value=["\']([^"\']*)["\'][^>]*type=["\']hidden["\']',
        html, re.IGNORECASE
    )
    for name, value in hidden_inputs + hidden_inputs2:
        if name not in data:
            data[name] = value

    return data


def _extract_form_action(html, page_url):
    action_match = re.search(r'<form[^>]+action=["\']([^"\']+)["\']', html, re.IGNORECASE)
    if action_match:
        action_url = action_match.group(1)
        if action_url.startswith("http"):
            return action_url
        parsed = urlparse(page_url)
        if action_url.startswith("/"):
            return f"{parsed.scheme}://{parsed.netloc}{action_url}"
        return urljoin(page_url, action_url)
    return page_url


async def solve_checkpoint(checkpoint_url, http_session):
    if not CAPTCHAAI_KEY:
        logger.warning("CAPTCHAAI_API_KEY not set, cannot solve checkpoint")
        return None

    try:
        headers = {
            'User-Agent': UA,
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
            'Accept-Language': 'en-US,en;q=0.9',
        }

        logger.info(f"Fetching checkpoint URL: {checkpoint_url[:80]}")
        async with http_session.get(
            checkpoint_url,
            headers=headers,
            timeout=aiohttp.ClientTimeout(total=20),
            allow_redirects=True,
        ) as resp:
            html = await resp.text()
            page_url = str(resp.url)
            status = resp.status
            logger.info(f"Checkpoint page status: {status}, url: {page_url[:80]}, html_len: {len(html)}")

        if not html or len(html) < 50:
            logger.warning(f"Checkpoint page empty or too short ({len(html)} chars)")
            return None

        turnstile_params = _extract_turnstile_params(html)
        sitekey = turnstile_params['sitekey']
        if not sitekey:
            logger.warning(f"No captcha sitekey found on checkpoint page. HTML snippet: {html[:500]}")
            return None

        captcha_type = _detect_captcha_type(html)
        logger.info(f"Detected {captcha_type} captcha, sitekey: {sitekey[:30]}..., action: {turnstile_params['action']}, cdata: {turnstile_params['cdata'] is not None}")

        token = None
        if captcha_type == 'turnstile':
            token = await solve_turnstile(sitekey, page_url, action=turnstile_params['action'], cdata=turnstile_params['cdata'])
        elif captcha_type == 'hcaptcha':
            token = await solve_hcaptcha(sitekey, page_url)

        if not token:
            if captcha_type == 'turnstile':
                logger.info("Turnstile failed, trying hCaptcha...")
                token = await solve_hcaptcha(sitekey, page_url)
            else:
                logger.info("hCaptcha failed, trying Turnstile...")
                token = await solve_turnstile(sitekey, page_url, action=turnstile_params['action'], cdata=turnstile_params['cdata'])

        if not token:
            logger.warning("Failed to solve captcha - no token received")
            return None

        logger.info(f"Got captcha token, submitting to checkpoint...")
        return await _submit_captcha_token(http_session, page_url, token, captcha_type, html)

    except Exception as e:
        logger.error(f"solve_checkpoint error: {e}", exc_info=True)
        return None


async def _submit_captcha_token(session, page_url, token, captcha_type, html):
    try:
        form_action = _extract_form_action(html, page_url)
        form_data = _extract_form_data(html)

        if captcha_type == "hcaptcha":
            form_data["h-captcha-response"] = token
            form_data["g-recaptcha-response"] = token
        elif captcha_type == "turnstile":
            form_data["cf-turnstile-response"] = token
        else:
            form_data["cf-turnstile-response"] = token
            form_data["h-captcha-response"] = token
            form_data["g-recaptcha-response"] = token

        headers = {
            'User-Agent': UA,
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
            'Accept-Language': 'en-US,en;q=0.9',
            'Content-Type': 'application/x-www-form-urlencoded',
            'Referer': page_url,
            'Origin': f"{urlparse(page_url).scheme}://{urlparse(page_url).netloc}",
        }

        logger.info(f"Submitting captcha token to: {form_action[:80]}, fields: {list(form_data.keys())}")

        async with session.post(
            form_action,
            data=form_data,
            headers=headers,
            allow_redirects=True,
            timeout=aiohttp.ClientTimeout(total=20),
        ) as resp:
            final_url = str(resp.url)
            status = resp.status
            text = await resp.text()
            logger.info(f"Captcha submit response: status={status}, final_url={final_url[:80]}")

            if "checkpoint" not in final_url.lower() and "captcha" not in final_url.lower():
                logger.info("Captcha solved successfully - redirected away from checkpoint")
                return True

            if "checkpoint" not in text.lower() and "captcha" not in text.lower():
                logger.info("Captcha solved successfully - no more captcha content on page")
                return True

            new_params = _extract_turnstile_params(text)
            if new_params['sitekey']:
                logger.warning(f"Captcha still present after submission (new sitekey found)")
            else:
                logger.warning(f"Captcha submission did not clear checkpoint. Status: {status}")

            return False

    except Exception as e:
        logger.error(f"_submit_captcha_token error: {e}", exc_info=True)
        return False
