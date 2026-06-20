import requests, json, time, re, sys
requests.packages.urllib3.disable_warnings()

results = []

# Test MSN endpoints
endpoints = [
    ("MSN CN Stock Page", "https://www.msn.cn/zh-cn/money/stockdetails/fi-a1ydos"),
    ("MSN CN Money Home", "https://www.msn.cn/zh-cn/money"),
    ("MSN COM Stock Page", "https://www.msn.com/en-us/money/stockdetails/fi-a1ydos"),
    ("Bing Finance Chart", "https://www.bing.com/api/v6/finance/chart/data?locale=en-US&symbol=AAPL&period=1M"),
]

for label, url in endpoints:
    try:
        s = time.time()
        r = requests.get(url, headers={
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
        }, timeout=20, verify=False, allow_redirects=True)
        t = time.time() - s
        
        # Check for stock data in response
        has_price = "price" in r.text.lower() or "open" in r.text.lower()
        has_chart = "chart" in r.text.lower() or "kline" in r.text.lower()
        
        # Try find embedded JSON data
        json_patterns = re.findall(r'\{[^}]{10,200}?(?:price|close|high|low|open)[^}]{10,200}?\}', r.text, re.IGNORECASE)
        
        results.append({
            "label": label,
            "status": r.status_code,
            "time": f"{t:.2f}s",
            "size_kb": len(r.text)//1024,
            "final_url": r.url[:100],
            "has_price_data": has_price,
            "has_chart_ref": has_chart,
            "json_matches": len(json_patterns),
            "sample": r.text[:300].replace("\n", " ")[:200]
        })
    except Exception as e:
        results.append({"label": label, "error": str(e)[:150]})

print(json.dumps(results, indent=2, ensure_ascii=False))
