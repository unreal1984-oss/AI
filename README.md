# Jira Data Center AI Agent

AI-агент для **Jira Data Center**: задачи и Insight/Assets по проектам.

**Рекомендуемый режим: Cursor Agent + MCP** (модели Cursor по подписке, без DeepSeek).  
Опционально: CLI с DeepSeek / OpenAI / Ollama.

## Cursor (рекомендуется)

У Cursor **нет** публичного `chat/completions` API.  
Jira-инструменты подключаются как **локальный MCP-сервер** — Agent в Cursor вызывает их своими моделями (**DeepSeek не нужен**, баланс DeepSeek не важен).

### Быстрый setup (Windows)

```powershell
git pull
.\scripts\setup_cursor_mcp.ps1
notepad .env
```

Скрипт создаст `.cursor\mcp.json`, который запускает MCP так:

```json
{
  "mcpServers": {
    "jira-dc": {
      "command": "cmd.exe",
      "args": ["/c", "${workspaceFolder}\\jira-agent-mcp.cmd"],
      "envFile": "${workspaceFolder}\\.env"
    }
  }
}
```

Лаунчер `jira-agent-mcp.cmd` сам находит `.venv\Scripts\python.exe` (это чинит ошибку Windows «не удаётся найти указанный путь»).

В `.env` заполните только Jira (пример):

```env
JIRA_BASE_URL=https://stage2-jira.stoloto.su
JIRA_USERNAME=...
JIRA_PASSWORD=...
JIRA_PROJECT_KEYS=NPTN,USA
ASSETS_OBJECT_SCHEMA_ID=8
JIRA_VERIFY_SSL=false
```

`DEEPSEEK_API_KEY` можно оставить пустым.

### Включить в Cursor

1. Откройте **эту папку** как workspace в Cursor  
2. **Settings → MCP** → сервер `jira-dc` должен быть зелёным / Enabled  
3. Command Palette → **Reload Window**  
4. Откройте **Agent** (не `.\jira-agent.cmd chat`) и спросите, например:  
   «Покажи открытые задачи NPTN и связанные активы»

Важно: `.\jira-agent.cmd chat` = отдельный CLI на DeepSeek (нужен баланс).  
**MCP в Cursor** = модели Cursor + локальные Jira tools (бесплатно в рамках подписки Cursor).

Проверка MCP без UI:

```powershell
.\.venv\Scripts\python.exe scripts\mcp_smoke.py
```

## Структура проекта

```
.
├── .env.example
├── .gitignore
├── README.md
├── pyproject.toml
├── requirements.txt
├── scripts/
│   └── bootstrap.sh
├── src/
│   └── jira_agent/
│       ├── __init__.py
│       ├── __main__.py
│       ├── agent.py          # цикл tool-calling (Ollama / cloud)
│       ├── assets_client.py  # /rest/assets/1.0/*
│       ├── cli.py            # CLI (typer)
│       ├── config.py         # настройки из .env
│       ├── jira_client.py    # /rest/api/2/*
│       ├── llm.py            # фабрика: deepseek | openai | ollama
│       ├── ollama_client.py  # локальный Ollama (опционально)
│       ├── openai_client.py  # DeepSeek / OpenAI-compatible cloud (CLI)
│       ├── mcp_server.py     # MCP для Cursor Agent
│       ├── prompts.py
│       ├── serializers.py
│       └── tools.py
├── .cursor/
│   └── mcp.json.example
└── tests/
    ├── test_agent.py
    └── test_core.py
```

## CLI + DeepSeek / OpenAI (опционально)

Если нужен отдельный CLI-чат вне Cursor:

1. Ключ API: https://platform.deepseek.com/api_keys  
2. В `.env`:

```env
LLM_PROVIDER=deepseek
DEEPSEEK_API_KEY=sk-...
OPENAI_BASE_URL=https://api.deepseek.com
OPENAI_MODEL=deepseek-chat
```

Модели DeepSeek:
- `deepseek-chat` — основной чат + tool calling (рекомендуется)
- `deepseek-reasoner` — рассуждения (tool calling ограничен)

Другие облака (тот же клиент):

| Провайдер | LLM_PROVIDER | OPENAI_BASE_URL | OPENAI_MODEL |
|---|---|---|---|
| DeepSeek | `deepseek` | `https://api.deepseek.com` | `deepseek-chat` |
| OpenAI | `openai` | `https://api.openai.com/v1` | `gpt-4o-mini` |
| OpenRouter | `openrouter` | `https://openrouter.ai/api/v1` | `deepseek/deepseek-chat` |

Локальный Ollama (если нужен):

```env
LLM_PROVIDER=ollama
OLLAMA_MODEL=qwen2.5:7b
```

Запуск:

```powershell
.\jira-agent.cmd doctor
.\jira-agent.cmd chat -p ITSM
.\jira-agent.cmd ask "Открытые задачи ITSM" -m deepseek-chat
```

## Используемые эндпоинты

| Назначение | Метод | Путь |
|---|---|---|
| Поиск задач | `POST` | `/rest/api/2/search` |
| Список проектов | `GET` | `/rest/api/2/project` |
| Поиск активов (AQL) | `GET` | `/rest/assets/1.0/aql/objects` |
| Объект актива | `GET` | `/rest/assets/1.0/object/{id}` |
| Поиск (IQL navlist) | `POST` | `/rest/assets/1.0/object/navlist/iql` |
| Тикеты актива | `GET` | `/rest/assets/1.0/objectconnectedtickets/{id}/tickets` |
| Схема активов | `GET` | `/rest/assets/1.0/objectschema/8` |

## Зависимости (без конфликтов)

Только лёгкий стек, **без LangChain / LlamaIndex / pydantic**:

- `httpx` — HTTP к Jira и DeepSeek/Ollama  
- `python-dotenv` — конфиг из `.env`  
- `typer` + `click` + `rich` — CLI  
- `tenacity` — ретраи транспорта  
- `pytest` + `respx` — тесты  

Версии зафиксированы в `requirements.txt`. На Windows/Python 3.14 **нет** сборки Rust (`pydantic-core`).

## Установка

Пакет лежит в `src/jira_agent` — его нужно поставить в venv (иначе будет `ModuleNotFoundError: No module named 'jira_agent'`).

### Windows (PowerShell)

```powershell
python --version
# если 3.14 — ок (после удаления pydantic). При проблемах поставьте 3.12 с python.org

.\scripts\bootstrap.ps1
copy .env.example .env
.\jira-agent.cmd doctor
.\jira-agent.cmd chat -p ITSM
```

Или вручную:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -U pip
pip install -r requirements.txt
pip install -e .
python -c "from jira_agent.cli import app; print('ok')"
```

### Linux / macOS

```bash
chmod +x scripts/bootstrap.sh
./scripts/bootstrap.sh
source .venv/bin/activate
cp .env.example .env
```

Ручная установка:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
pip install -e .
python -c "from jira_agent.cli import app; print('ok')"
```

Запуск **без** `pip install -e .` (через `PYTHONPATH`):

```bash
python run.py doctor
# или
PYTHONPATH=src python -m jira_agent doctor
```

Заполните `.env`:

```env
JIRA_BASE_URL=https://your-jira.example.com
JIRA_USERNAME=your.user
JIRA_PASSWORD=your-password-or-api-token
JIRA_PROJECT_KEYS=ITSM,PROJ
ASSETS_OBJECT_SCHEMA_ID=8

LLM_PROVIDER=deepseek
DEEPSEEK_API_KEY=sk-...
OPENAI_BASE_URL=https://api.deepseek.com
OPENAI_MODEL=deepseek-chat
```

## Команды

```powershell
# Проверка Jira + Assets + DeepSeek
.\jira-agent.cmd doctor

# Интерактивный чат
.\jira-agent.cmd chat -p ITSM,PROJ

# Один вопрос
.\jira-agent.cmd ask "Какие открытые задачи в ITSM и какие активы с ними связаны?" -p ITSM

# Прямые запросы без LLM
.\jira-agent.cmd projects
.\jira-agent.cmd issues -p ITSM --jql "status != Done" -n 30
.\jira-agent.cmd schema
.\jira-agent.cmd assets --projects ITSM
.\jira-agent.cmd asset 12345 --tickets
```

Либо: `python run.py doctor`

## Как работает агент

1. Пользователь задаёт вопрос.  
2. DeepSeek Cloud получает system prompt + список tools (OpenAI-compatible).  
3. Модель вызывает инструменты (`search_issues`, `search_assets_aql`, …).  
4. Клиенты ходят в Jira DC по указанным REST API.  
5. Результаты сжимаются сериализаторами и возвращаются модели.  
6. Модель формирует итоговый ответ на русском (по умолчанию).

Инструменты агента:

- `list_projects`
- `search_issues` / `get_issue`
- `get_object_schema`
- `search_assets_aql` / `search_assets_iql` / `search_assets_by_projects`
- `get_asset` / `get_asset_tickets`

`search_assets_by_projects` строит AQL по схеме `ASSETS_OBJECT_SCHEMA_ID` и атрибутам `Project` / `Project Key` / `Jira Project`. Если в вашей схеме другие имена атрибутов — используйте `search_assets_aql` с явным AQL.

## Тесты

```bash
source .venv/bin/activate
pytest -q
```

## Troubleshooting

### `Preparing metadata (pyproject.toml) ... error` / `SOABI: cp314-win_amd64` / `rustc`

Это была сборка **pydantic-core** (Rust) под Python 3.14 на Windows. В текущей версии агента **pydantic удалён**.

Обновите код и поставьте зависимости заново:

```powershell
git pull
Remove-Item -Recurse -Force .venv -ErrorAction SilentlyContinue
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -U pip
pip install -r requirements.txt
pip install -e .
```

Если всё ещё тянется старый `requirements.txt` с pydantic — убедитесь, что в файле **нет** строк `pydantic` / `pydantic-settings`.

### Windows: `jira-agent` не распознан

В PowerShell команда из PATH появляется только после editable-install **и** активации venv.

Самый простой запуск (без PATH):

```powershell
.\jira-agent.cmd doctor
.\jira-agent.cmd chat -p ITSM
# или
python run.py chat -p ITSM
```

Чтобы работало как `jira-agent`:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
pip install -e .
jira-agent doctor
```

Проверка: `Get-Command jira-agent` должен показать `.venv\Scripts\jira-agent.exe`.

### `ModuleNotFoundError: No module named 'jira_agent'`

Пакет не установлен в текущий Python:

```powershell
.\.venv\Scripts\Activate.ps1
pip install -e .
python -c "from jira_agent.cli import app; print('ok')"
```

Или без установки: `.\jira-agent.cmd chat -p ITSM`

## SSL / корпоративный Jira / DeepSeek

Если сертификат самоподписанный (часто корпоративный SSL-inspection):

```env
# Jira
JIRA_VERIFY_SSL=false

# DeepSeek / cloud LLM
LLM_VERIFY_SSL=false
```

Лучше указать корпоративный CA, чем отключать проверку:

```env
LLM_CA_BUNDLE=C:\certs\corp-root-ca.pem
JIRA_VERIFY_SSL=true
```

### Assets `401 Unauthorized`

На Jira DC плагин Assets/Insight часто **не принимает Bearer PAT**.

В `.env` используйте Basic:

```env
JIRA_USERNAME=your.user
JIRA_PASSWORD=your-password
# либо пароль = PAT:
# JIRA_PAT=your-pat
# (USERNAME обязателен)

JIRA_VERIFY_SSL=false
ASSETS_OBJECT_SCHEMA_ID=8
ASSETS_API_PREFIX=auto
```

Проверка:

```powershell
.\jira-agent.cmd doctor --insecure
```

Если Jira OK, а Assets 401 — у пользователя нет доступа к Assets/Insight или неверный логин.  
`projects: 0` при OK значит учётка видит API, но без Browse Projects (или пустой стенд).

В `.env` добавьте `LLM_VERIFY_SSL=false`, перезапустите чат:

```powershell
.\jira-agent.cmd chat -p ITSM
```

## Лицензия

MIT
