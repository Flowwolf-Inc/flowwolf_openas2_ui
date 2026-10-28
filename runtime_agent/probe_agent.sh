#!/bin/bash
TOKEN=phase2-dev-token-change-me
for ip in 127.0.0.1 10.255.255.254; do
  echo -n "try $ip: "
  code=$(curl -s -o /tmp/agent_ping.json -w "%{http_code}" -m 3 -X POST "http://$ip:9475/v1/ping" \
    -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" \
    -d '{"action":"ping"}' || echo fail)
  echo "$code"
  cat /tmp/agent_ping.json 2>/dev/null; echo
done
