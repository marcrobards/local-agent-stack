# Shopping Agent App — Greenfield Build Spec

## Overview

Build a purpose-built iPad web app that lets a single user (Danielle) describe what she's looking for, trigger an AI-powered product search across multiple retail sites, and browse results as tappable product cards. This is a greenfield project — build everything from scratch with no dependency on any existing code in the repo.

The app has two containers: a React frontend served by Bun + Hono, and a FastAPI backend that handles conversation, search execution, and persistence. Both live under `src/shopping-app/` in the `local-agent-stack` repo and are added to the root `docker-compose.yml`.

Push notifications are out of scope for this build and will be added in a follow-up spec.

---

## Repository

- Repo root: `~/local-agent-stack` on host `lenovo-laptop`
- All new code lives under: `src/shopping-app/`
- Add both new services to the existing root `docker-compose.yml`
- Do not modify or depend on any other code in the repo

---

## Suggested file structure

```
src/shopping-app/
├── frontend/
│   ├── Dockerfile
│   ├── package.json
│   ├── tsconfig.json
│   └── src/
│       ├── server.ts           # Bun + Hono entry point (serves SPA + proxies /api)
│       ├── app/
│       │   ├── App.tsx
│       │   ├── SearchList.tsx
│       │   ├── SearchDetail.tsx
│       │   ├── ProductCard.tsx
│       │   ├── ClarifyChat.tsx
│       │   └── ...
│       └── public/
│           ├── manifest.json
│           └── sw.js
└── backend/
    ├── Dockerfile
    ├── requirements.txt
    ├── main.py                 # FastAPI entry point
    ├── db.py                   # SQLite setup and helpers
    ├── routers/
    │   ├── searches.py
    │   └── preferences.py
    ├── services/
    │   ├── clarify.py          # Anthropic Claude Sonnet conversation
    │   ├── search.py           # Browser Use Cloud + Anthropic search execution
    │   └── preferences.py      # dual-write to SQLite + Qdrant
    └── models.py               # Pydantic models
```

---

## Docker Compose additions

```yaml
shopping-frontend:
  build:
    context: ./src/shopping-app/frontend
  ports:
    - "3001:3001"
  environment:
    - API_URL=http://shopping-backend:8000
  depends_on:
    - shopping-backend
  restart: unless-stopped

shopping-backend:
  build:
    context: ./src/shopping-app/backend
  ports:
    - "8000:8000"
  volumes:
    - shopping_data:/data
  env_file:
    - .env
  restart: unless-stopped

volumes:
  shopping_data:
```

Required `.env` variables (already expected to exist in root `.env`):
- `ANTHROPIC_API_KEY`
- `BROWSER_USE_API_KEY`

Qdrant is already running in the stack at `http://qdrant:6333` on the internal Docker network. The backend should connect to it there.

---

## Backend: FastAPI

### Runtime
- Python 3.11
- FastAPI + Uvicorn
- aiosqlite for async SQLite access
- httpx for any outbound HTTP
- `anthropic` Python SDK for Claude Sonnet
- `browser-use-sdk` for Browser Use Cloud
- `qdrant-client` for preference vector storage

### SQLite

Database file: `/data/shopping.db` (persisted via Docker volume)

```sql
CREATE TABLE IF NOT EXISTS searches (
    id          TEXT PRIMARY KEY,
    created_at  DATETIME DEFAULT (datetime('now')),
    updated_at  DATETIME DEFAULT (datetime('now')),
    status      TEXT DEFAULT 'clarifying',
    -- status values: clarifying | searching | complete | failed
    spec        TEXT,        -- JSON: confirmed search specification
    results     TEXT,        -- JSON array of product cards, null until complete
    error       TEXT         -- error message if status = failed
);

CREATE TABLE IF NOT EXISTS messages (
    id          TEXT PRIMARY KEY,
    search_id   TEXT REFERENCES searches(id),
    role        TEXT,        -- 'user' | 'assistant'
    content     TEXT,
    created_at  DATETIME DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS preferences (
    id          TEXT PRIMARY KEY,
    key         TEXT UNIQUE,
    value       TEXT,
    updated_at  DATETIME DEFAULT (datetime('now'))
);
```

---

## Backend: API routes

All routes prefixed `/api/v1`.

### Searches

#### `GET /api/v1/searches`
All searches, newest first.
```json
[
  {
    "id": "uuid",
    "created_at": "iso8601",
    "updated_at": "iso8601",
    "status": "complete",
    "spec": { ... },
    "result_count": 6
  }
]
```

#### `POST /api/v1/searches`
Create a new search session. Returns immediately.
```json
{ "id": "uuid", "status": "clarifying" }
```

#### `GET /api/v1/searches/{id}`
Full search detail.
```json
{
  "id": "uuid",
  "status": "complete",
  "spec": { ... },
  "messages": [
    { "id": "uuid", "role": "user", "content": "...", "created_at": "iso8601" }
  ],
  "results": [
    {
      "name": "Blue Linen Tote",
      "price": "$34.00",
      "store": "Etsy",
      "image_url": "https://...",
      "product_url": "https://..."
    }
  ],
  "error": null
}
```

#### `POST /api/v1/searches/{id}/messages`
Send a clarifying message. Calls Claude Sonnet with the full conversation history and returns the assistant reply. Also recalls relevant preferences from Qdrant and includes them in the system prompt.
```json
// request
{ "content": "I'm looking for a blue linen tote bag" }

// response
{ "id": "uuid", "role": "assistant", "content": "Got it — any size preference or budget?" }
```

#### `POST /api/v1/searches/{id}/confirm`
Danielle confirms the spec and triggers the search. Sets status to `searching`, spawns a background task, returns immediately.
```json
// response
{ "status": "searching" }
```

The background task:
1. Calls `services/search.py` with the confirmed spec
2. The search service uses Browser Use Cloud + Claude Sonnet to decide which retail sites to search based on the spec, then searches them
3. On success: writes product cards to `searches.results`, sets `status = 'complete'`
4. On failure: sets `status = 'failed'`, writes error message

#### `POST /api/v1/searches/{id}/refine`
Danielle adds context after seeing results. Appends her message and a brief assistant acknowledgment to the conversation, then triggers another search round with the full updated context. Sets status to `searching`.
```json
// request
{ "content": "Actually needs to be under $25, preferably natural colors" }

// response
{ "status": "searching" }
```

#### `GET /api/v1/searches/{id}/status`
Lightweight poll endpoint. Frontend calls this every 10 seconds while status is `searching`.
```json
{ "status": "searching" }
// or
{ "status": "complete" }
// or
{ "status": "failed", "error": "..." }
```

### Preferences

#### `GET /api/v1/preferences`
All preferences as key-value pairs.
```json
[{ "key": "budget_range", "value": "under $50" }]
```

#### `POST /api/v1/preferences`
Upsert a preference. Writes to SQLite and also embeds + stores in Qdrant under `user_id: "danielle"` using the existing Qdrant instance at `http://qdrant:6333`.
```json
// request
{ "key": "budget_range", "value": "under $50" }
```

---

## Backend: search service

`services/search.py` is responsible for the full search execution. Design notes for the agent:

- Receives the confirmed spec (a structured description of what Danielle wants) plus full conversation history
- Uses Claude Sonnet to reason about which retail sites are most appropriate to search given the spec — do not hardcode a fixed list of sites
- Uses Browser Use (see https://docs.browser-use.com/cloud/llms.txt for instructions) to browse and extract product results from chosen sites
- Each result must have at minimum: `name`, `price`, `store`, `product_url`
- `image_url` is best-effort — null is acceptable
- `product_url` must be a direct link to the specific product page, not a search results page
- Aim for 5–15 results total across all sites searched
- The search is expected to take 5–10 minutes — this is normal and acceptable

---

## Backend: clarify service

`services/clarify.py` handles the conversation stage using Claude Sonnet (`claude-sonnet-4-20250514`).

System prompt should instruct the model to:
- Help Danielle describe what she's looking for in enough detail to search for it effectively
- Ask focused clarifying questions (one at a time) about things that would meaningfully affect results: item type, color, size, material, price range, occasion/use
- Recall and reference any relevant stored preferences (passed in from Qdrant at call time)
- When enough detail exists, produce a structured search spec as a JSON object and signal that it's ready — do not ask unnecessary questions
- Keep tone friendly and concise — this is a tool, not a chatbot

The structured spec produced at the end of clarification should be stored in `searches.spec` and passed to the search service. Minimum fields: `item_description`, `color`, `price_max`, `notes`.

---

## Frontend: Bun + Hono + React

### Server (`server.ts`)
- Serves the built React SPA for all non-API routes
- Proxies all `/api/*` requests to `http://shopping-backend:8000`
- Listens on port 3001

### PWA
- `public/manifest.json`: app name "Shopping", `display: standalone`, appropriate icons
- `public/sw.js`: minimal service worker (cache shell only — just enough for iOS to recognize it as a PWA installable to Home Screen)
- Once added to Home Screen on iPad, the app launches full-screen with no Safari UI

### Screens

#### Screen 1 — Search list (home)

- Header: "Shopping" + "New Search" button (prominent, top right)
- Scrollable list of past searches, newest first
- Each row shows: time ago, status badge, brief spec summary (e.g. "Blue linen tote bag")
  - Status badges: "Searching…" (animated), "Done", "Failed"
- Tapping a row opens the search detail
- Empty state: large friendly prompt to tap "New Search"
- Tapping "New Search" calls `POST /api/v1/searches` and navigates to the new search detail

#### Screen 2 — Search detail

One screen with three visual states driven by `status`.

**Clarifying state**

- Conversation thread, scrollable, newest at bottom
- User messages right-aligned, assistant messages left-aligned
- Sticky text input + Send at the bottom (stays above the iOS keyboard)
- After the assistant has produced a spec and signaled readiness, a prominent "Search for this →" button appears above the input
- Danielle can also tap "Search for this →" at any point to proceed regardless
- Tapping "Search for this →" calls `POST /confirm`

**Searching state**

- Spec summary card at top (the confirmed spec, readable plain English)
- Friendly animated loading message below: "Searching…" — can cycle through subtle messages like "Browsing Etsy…", "Checking Target…" etc.
- No input during this state
- Poll `GET /status` every 10 seconds; on `complete` or `failed`, re-fetch full search and transition — no full page reload

**Results state**

- Spec summary card at top, collapsible
- 2-column product card grid, scrollable
- Each card:
  - Product image, full card width, fixed aspect ratio (4:3), `object-fit: cover`
  - Neutral grey placeholder if image is null or fails to load
  - Product name: 2 lines max, truncated with ellipsis
  - Price: prominent, larger text
  - Store name: small, muted, below price
  - Entire card is tappable → opens `product_url` in a new Safari tab
- Below the grid: "Not quite right? Tell me more:" + text input + Send button
- Submitting calls `POST /refine` and transitions to searching state

**Failed state**

- Clear error message
- "Try again" button calls `POST /confirm` again (retries the search with the same spec)

### Design

- **iPad-first** — design for iPad portrait in Safari
- **Touch targets** — minimum 44×44pt for all interactive elements
- **Typography** — system font stack only: `-apple-system, BlinkMacSystemFont, sans-serif`
- **Color** — white background, one accent color (your choice, something calm), standard grey for muted text
- **Spacing** — generous. This is used on a couch, not a desk.
- **No auth** — local network only, no login

---

## Acceptance criteria

- [ ] `docker compose up` starts `shopping-frontend` and `shopping-backend` without errors
- [ ] Navigating to `http://lenovo-laptop.local:3001` on iPad opens the app
- [ ] Adding to iPad Home Screen and launching works full-screen
- [ ] Creating a new search and sending clarifying messages works; assistant replies with Claude Sonnet
- [ ] Tapping "Search for this →" triggers a background search and shows the searching state
- [ ] UI polls and transitions to results without a full reload when search completes
- [ ] Results render as a 2-column card grid; tapping a card opens the product URL in Safari
- [ ] Failed search shows error state with a working retry button
- [ ] Refinement input triggers a new search round within the same search session
- [ ] Past searches appear on the home screen and can be reopened

---

## Explicitly out of scope

- Push notifications (APNs / web push) — follow-up spec
- Color verification
- Multiple users
- Any UI or feature not described above
