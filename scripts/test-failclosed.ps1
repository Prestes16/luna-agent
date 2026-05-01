$ErrorActionPreference = "Stop"

$payload = "D:\luna-agent\scripts\payloads\broken_workspace_chat.json"

Write-Host "== upload payload =="
scp $payload cleiton@209.200.246.165:/tmp/luna_broken_chat.json

Write-Host "== preparar workspace quebrado e subir instancia temporaria =="
ssh cleiton@209.200.246.165 'cd ~/luna-agent && rm -rf workspaces/luna-agent-broken && cp -r workspaces/luna-agent workspaces/luna-agent-broken && rm -f workspaces/luna-agent-broken/NEXT_STEPS.md && docker rm -f luna-agent-broken-test >/dev/null 2>&1 || true && docker run -d --name luna-agent-broken-test -p 8010:8000 -e LUNA_ACTIVE_WORKSPACE=luna-agent-broken --env-file ~/luna-agent/.env -v ~/luna-agent/app:/app/app:ro -v ~/luna-agent/prompts:/app/prompts:ro -v ~/luna-agent/workspaces:/app/workspaces:ro luna-agent-luna-agent >/dev/null && sleep 3 && echo HEALTH: && curl -s http://127.0.0.1:8010/health'

Write-Host "== testar chat =="
ssh cleiton@209.200.246.165 'echo CHAT: && curl -s -X POST http://127.0.0.1:8010/chat -H "Content-Type: application/json" --data-binary @/tmp/luna_broken_chat.json'

Write-Host "== limpeza =="
ssh cleiton@209.200.246.165 'docker rm -f luna-agent-broken-test >/dev/null 2>&1 || true; rm -rf ~/luna-agent/workspaces/luna-agent-broken; rm -f /tmp/luna_broken_chat.json; echo ok'
