import urllib.request

TOKEN = "phase2-dev-token-change-me"
URLS = [
	"http://127.0.0.1:9475/v1/ping",
	"http://172.18.48.1:9475/v1/ping",
	"http://10.255.255.254:9475/v1/ping",
	"http://192.168.31.116:9475/v1/ping",
]
body = b'{"action":"ping"}'
for url in URLS:
	req = urllib.request.Request(
		url,
		data=body,
		headers={
			"Authorization": f"Bearer {TOKEN}",
			"Content-Type": "application/json",
		},
		method="POST",
	)
	try:
		with urllib.request.urlopen(req, timeout=3) as resp:
			print(url, "OK", resp.read()[:120])
	except Exception as exc:
		print(url, "FAIL", exc)
