# Jira Data Center AI Agent (Ollama)

Локальный AI-агент для **Jira Data Center**: отвечает на вопросы по **задачам** и **Insight/Assets** в указанных проектах. LLM — **Ollama** на вашей машине (без облачных API).

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
│       ├── agent.py          # цикл tool-calling с Ollama
│       ├── assets_client.py  # /rest/assets/1.0/*
│       ├── cli.py            # CLI (typer)
│       ├── config.py         # настройки из .env
│       ├── jira_client.py    # /rest/api/2/*
│       ├── ollama_client.py  # /api/chat, /api/tags
│       ├── prompts.py
│       ├── serializers.py    # компактный JSON для контекста модели
│       └── tools.py          # инструменты агента
└── tests/
    ├── test_agent.py
    └── test_core.py
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

Только лёгкий стек, **без LangChain / LlamaIndex**:

- `httpx` — HTTP к Jira и Ollama  
- `pydantic` + `pydantic-settings` — конфиг  
- `typer` + `rich` — CLI  
- `tenacity` — ретраи транспорта  
- `pytest` + `respx` — тесты  

Версии зафиксированы в `requirements.txt`.

## Установка

Пакет лежит в `src/jira_agent` — его нужно поставить в venv (иначе будет `ModuleNotFoundError: No module named 'jira_agent'`).

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

### `ModuleNotFoundError: No module named 'jira_agent'`

Значит используется Python, куда пакет не установлен. Исправление:

```bash
# из корня репозитория
source .venv/bin/activate   # если venv ещё нет — ./scripts/bootstrap.sh
pip install -e .
which python                # должен указывать на .../AI/.venv/bin/python
python -c "from jira_agent.cli import app; print('ok')"
```

Либо без установки:

```bash
python run.py chat -p ITSM
```

## SSL / корпоративный Jira

Если сертификат самоподписанный:

```env
JIRA_VERIFY_SSL=false
```

## Лицензия

MIT
