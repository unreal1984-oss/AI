# Jira Data Center AI Agent

AI-агент для **Jira Data Center**: отвечает на вопросы по **задачам** и **Insight/Assets** в указанных проектах.

LLM: **локальный Ollama** или **облачные модели** через OpenAI-compatible API (OpenAI, OpenRouter, DeepSeek, Groq и т.д.).

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
│       ├── llm.py            # фабрика провайдеров (ollama | openai)
│       ├── ollama_client.py  # локальный Ollama
│       ├── openai_client.py  # облачный OpenAI-compatible API
│       ├── prompts.py
│       ├── serializers.py
│       └── tools.py
└── tests/
    ├── test_agent.py
    └── test_core.py
```

## Облачные модели

В `.env`:

```env
LLM_PROVIDER=openai
OPENAI_API_KEY=sk-...
OPENAI_BASE_URL=https://api.openai.com/v1
OPENAI_MODEL=gpt-4o-mini
```

Примеры базовых URL:

| Провайдер | OPENAI_BASE_URL | Пример OPENAI_MODEL |
|---|---|---|
| OpenAI | `https://api.openai.com/v1` | `gpt-4o-mini` |
| OpenRouter | `https://openrouter.ai/api/v1` | `openai/gpt-4o-mini` |
| DeepSeek | `https://api.deepseek.com` | `deepseek-chat` |
| Groq | `https://api.groq.com/openai/v1` | `llama-3.3-70b-versatile` |

Локальный режим (как раньше):

```env
LLM_PROVIDER=ollama
OLLAMA_MODEL=qwen2.5:7b
```

Переключение без правки `.env`:

```bash
jira-agent chat --provider openai -m gpt-4o-mini -p ITSM
jira-agent ask "Открытые задачи" --provider ollama -m qwen2.5:7b
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

- `httpx` — HTTP к Jira и Ollama  
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
.\.venv\Scripts\Activate.ps1
jira-agent doctor
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
# либо вместо Basic:
# JIRA_PAT=your-personal-access-token

JIRA_PROJECT_KEYS=ITSM,PROJ
ASSETS_OBJECT_SCHEMA_ID=8

OLLAMA_BASE_URL=http://127.0.0.1:11434
OLLAMA_MODEL=qwen2.5:7b
```

### Рекомендуемые локальные модели Ollama

Для **tool calling** лучше всего:

- `qwen2.5:7b` (по умолчанию)
- `qwen2.5-coder:latest`
- `llama3.1:latest`

Также подходят для ответов (tool calling слабее): `llama3.2:latest`, `gpt-oss:20b`, `DeepSeek-Coder-V2:latest`, `kimi-k2.7-code:cloud`.

Смена модели:

```bash
jira-agent chat -m qwen2.5-coder:latest
# или
OLLAMA_MODEL=llama3.1:latest jira-agent ask "Открытые задачи ITSM"
```

## Команды

```bash
# Проверка Jira + Assets + Ollama
jira-agent doctor

# Интерактивный чат
jira-agent chat -p ITSM,PROJ

# Один вопрос
jira-agent ask "Какие открытые задачи в ITSM и какие активы с ними связаны?" -p ITSM

# Прямые запросы без LLM
jira-agent projects
jira-agent issues -p ITSM --jql 'status != Done' -n 30
jira-agent schema
jira-agent assets --projects ITSM
jira-agent assets --aql 'objectSchemaId = 8 AND Name LIKE "srv"'
jira-agent assets --iql 'Name LIKE "srv"'
jira-agent asset 12345 --tickets
```

Либо через модуль:

```bash
python -m jira_agent doctor
```

## Как работает агент

1. Пользователь задаёт вопрос.  
2. Ollama получает system prompt + список tools (OpenAI-compatible).  
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

### `ModuleNotFoundError: No module named 'jira_agent'`

Значит используется Python, куда пакет не установлен. Исправление:

```powershell
.\.venv\Scripts\Activate.ps1
pip install -e .
python -c "from jira_agent.cli import app; print('ok')"
```

Или без установки: `python run.py chat -p ITSM`

## SSL / корпоративный Jira

Если сертификат самоподписанный:

```env
JIRA_VERIFY_SSL=false
```

## Лицензия

MIT
