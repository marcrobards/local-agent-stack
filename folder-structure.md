# Folder Structure

Generated: 2026-03-28 (updated)

```
local-agent-stack/
├── CLAUDE.md
├── README.md
├── deploy
├── docker-compose.yml
├── docs/
│   ├── HANDOFF.md
│   ├── architecture.md
│   ├── decisions.md
│   ├── memory-api.md
│   ├── server-specs.md
│   └── setup.md
└── src/
    ├── agent-memory-layer/
    │   ├── Dockerfile
    │   ├── docker-compose.yml
    │   ├── memory-layer-spec.md
    │   ├── requirements.txt
    │   ├── memory/
    │   │   ├── __init__.py
    │   │   ├── client.py
    │   │   └── config.py
    │   └── tests/
    │       ├── memory_chat.py
    │       └── smoke_test.py
    └── workflows/
        └── online-shopping/
            ├── CONTEXT.md
            ├── 01-clarify-request/
            │   ├── PROMPT.md
            │   └── output/
            ├── 02-search/
            │   ├── PROMPT.md
            │   ├── output/
            │   └── tools/
            │       └── search.py
            ├── 02-verify/
            │   ├── PROMPT.md
            │   ├── output/
            │   └── tools/
            │       └── fetch_page.py
            ├── 02a-color-verify/
            │   ├── PROMPT.md
            │   ├── output/
            │   └── tools/
            │       └── fetch_images.py
            ├── 03-present/
            │   ├── PROMPT.md
            │   └── output/
            └── tests/
                ├── smoke_test.py
                └── smoke_test_02a.py
```
