import sys
import json
import re

def parse_proxy(raw):
    raw = raw.strip()
    if raw.startswith("http://") or raw.startswith("https://") or raw.startswith("socks5://") or raw.startswith("socks4://"):
        return raw
    parts = raw.split(":")
    if len(parts) == 2:
        host, port = parts
        if port.isdigit():
            return f"http://{host}:{port}"
    elif len(parts) == 4:
        host, port, user, pwd = parts
        if port.isdigit():
            return f"http://{user}:{pwd}@{host}:{port}"
    return None

def validate_format(raw):
    raw = raw.strip()
    if not raw:
        return False, "Empty proxy"
    
    parsed = parse_proxy(raw)
    if not parsed:
        return False, "Invalid format. Use: ip:port, ip:port:user:pass, http://ip:port, socks5://ip:port"
    return True, parsed

def main():
    if len(sys.argv) < 2:
        print(json.dumps({"valid": False, "error": "No proxy provided"}))
        return

    action = sys.argv[1]
    
    if action == "validate":
        raw = sys.argv[2] if len(sys.argv) > 2 else ""
        valid, result = validate_format(raw)
        if not valid:
            print(json.dumps({"valid": False, "error": result}))
            return
        
        try:
            import urllib.request
            import urllib.error
            proxy_url = result
            
            if proxy_url.startswith("socks"):
                print(json.dumps({"valid": True, "proxy": raw, "tested": False, "message": "SOCKS proxy format valid (not live-tested)"}))
                return
            
            proxy_handler = urllib.request.ProxyHandler({"http": proxy_url, "https": proxy_url})
            opener = urllib.request.build_opener(proxy_handler)
            req = urllib.request.Request("http://httpbin.org/ip", method="GET")
            req.add_header("User-Agent", "Mozilla/5.0")
            response = opener.open(req, timeout=10)
            data = json.loads(response.read().decode())
            print(json.dumps({"valid": True, "proxy": raw, "tested": True, "ip": data.get("origin", ""), "message": "Proxy working"}))
        except Exception as e:
            err_str = str(e)[:200]
            print(json.dumps({"valid": True, "proxy": raw, "tested": False, "message": f"Format valid but connection failed: {err_str}"}))
    
    elif action == "format_check":
        raw = sys.argv[2] if len(sys.argv) > 2 else ""
        valid, result = validate_format(raw)
        print(json.dumps({"valid": valid, "error": "" if valid else result, "proxy": raw if valid else ""}))

if __name__ == "__main__":
    main()
