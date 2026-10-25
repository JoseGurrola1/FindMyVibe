# FindMyVibe 🐾

An AI-powered, Akinator-style game that guesses where you actually want to go.
Tell Puss what you're after, answer a few playful questions, and he guesses a
**real place** nearby, with photos, opening hours and directions. Say "not my
vibe" and he asks a smarter follow-up and tries again.

**Live:** https://findmyvibe.tech

---

## How it plays

**Solo quest**
1. Type what, where and when in one box: *"live music in Austin tonight"*.
2. Puss asks ~3 questions (multiple choice, or type your own answer).
3. He reveals a real place: photo, rating, today's hours, and why it fits.
4. Reject it with a reason ("too loud", "too pricey") and he asks a targeted
   follow-up, then guesses again. Accept it to open directions.

**Group quest** (`/group`)
1. The host creates a party and shares the code (e.g. `VIBE-6B5E`) or invite link.
2. Everyone answers their own questions on their own phone.
3. Puss blends everyone's answers and finds 3 places, with a line per person
   on what each place offers them.
4. The party votes live. Ties are settled by a coin flip.

## Features

- **Adaptive questions** from Google Gemini, using your earlier answers and rejection reasons.
- **Real places only** from SerpApi (Google Maps results). Gemini picks from the list and can't invent a place.
- **Opening hours**: "tonight after 8pm" skips places that are closed then; every card shows the hours.
- **Group mode** with rooms, live sync, per-person reasons and voting.
- **Works when things break**: if Gemini or SerpApi fails or times out, built-in questions, keyword search and saved results keep the game going.
- **Rate limiting** to protect API quota on the public site.

## How it works

```
Browser (Next.js) ──/api──> FastAPI backend
                               ├─ Gemini: questions, search query, picks, reading the start sentence
                               ├─ SerpApi (Google Maps): real places, photos, hours
                               ├─ hours.py: open / closed at the requested time
                               ├─ fallback.py: works without Gemini/SerpApi
                               └─ SQLite (data/groups.db): group rooms
```

In production, Caddy serves both on one domain with HTTPS: `/api/*` goes to
FastAPI and everything else to Next.js (see [`deploy/`](deploy/README.md)).

---

## Run it locally

**You need:** Python 3.12+, Node.js 20.9+ (22 recommended), and two API keys:
- **SerpApi**: https://serpapi.com (the free plan works for testing)
- **Gemini**: https://aistudio.google.com/apikey

### 1. Backend (terminal 1)

**Windows (PowerShell)**
```powershell
cd FindMyVibe
python -m venv .venv
.\.venv\Scripts\Activate.ps1      # if blocked: Set-ExecutionPolicy -Scope Process Bypass
pip install -r requirements.txt
```

**macOS / Linux**
```bash
cd FindMyVibe
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

Create a file named `.env` in the project folder (it's git-ignored, so never commit it):
```
SERPAPI_KEY=your_serpapi_key
GEMINI_API_KEY=your_gemini_key
```

Start the API:
```bash
uvicorn main:app --reload --port 8000
```
Check http://127.0.0.1:8000/docs for the interactive API page.

> "uvicorn is not recognized"? The virtual environment isn't active in this
> terminal. Run the activate line again (your prompt should start with `(.venv)`).

### 2. Frontend (terminal 2)

```bash
cd FindMyVibe/frontend
npm ci
npm run dev
```
Open http://localhost:3000. In development, Next.js forwards `/api` calls to
the backend on port 8000 (see `frontend/next.config.ts`), so both must be running.

## Tests

No API keys or network needed: Gemini and SerpApi are faked.
```bash
pip install pytest httpx
python -m pytest tests -v
```

| File | Covers |
|---|---|
| `test_fallback.py` | The game keeps going when Gemini or SerpApi fail |
| `test_intro.py` | Reading "what, where, when" from the start sentence; answer hints |
| `test_city_context.py` | City / what / when reach the search and Gemini |
| `test_hours.py` | Opening-hours parsing and open/closed decisions |
| `test_groups.py` | Rooms, joining, per-member questions, group picks, voting, ties |
| `test_ratelimit.py` | Per-visitor and overall limits |
| `test_places_no_key_leak.py` | The SerpApi key never appears in errors or logs |

## Configuration

Set these in `.env` (backend):

| Variable | Default | What it does |
|---|---|---|
| `SERPAPI_KEY` | (required) | Google Maps results via SerpApi |
| `GEMINI_API_KEY` | (optional) | Without it, the game runs on the built-in fallbacks |
| `RATE_LIMIT_PER_MINUTE` | `100` | API calls per visitor (IP) per minute |
| `RATE_LIMIT_PER_HOUR` | `1000` | API calls per visitor per hour |
| `RATE_LIMIT_GLOBAL_PER_HOUR` | `1000` | API calls per hour across everyone |
| `RATE_LIMIT_ENABLED` | `true` | Set to `false` to turn limits off |
| `GROUPS_DB` | `data/groups.db` | Where group rooms are stored |

The Gemini model is set in `gemini_ai.py` (`MODEL`).

## API

| Method | Path | Purpose |
|---|---|---|
| `POST` | `/api/game/next` | Solo: next question or a guess. First turn sends `intro`; later turns send `city`, `what`, `when`, `history`, `rejected_ids`, `rejection_feedback`, `tz` |
| `POST` | `/api/groups` | Create a party → `room_id`, `code`, `member_token` |
| `POST` | `/api/groups/join` | Join with a code |
| `GET` | `/api/groups/{room_id}` | Room state (polled every ~2s; not rate-limited) |
| `POST` | `/api/groups/{room_id}/start` | Host starts the questions |
| `POST` | `/api/groups/{room_id}/turn` | Answer, get your next question |
| `POST` | `/api/groups/{room_id}/search` | Host: find places without waiting for everyone |
| `POST` | `/api/groups/{room_id}/vote` | Vote for an option |
| `POST` | `/api/groups/{room_id}/reveal` | Host: reveal the winner now |

Group room calls need the `X-Member-Token` header returned by create/join.

## Project layout

```
main.py             FastAPI app: solo game, rate limiting, search with fallbacks
group_routes.py     Group mode API
groups.py           Group rooms and members (SQLite)
gemini_ai.py        All Gemini prompts (questions, search, picks, start sentence)
places.py           SerpApi Google Maps search
hours.py            Opening hours vs. "tonight", "Saturday brunch", ...
fallback.py         Built-in questions, keyword search, ranking, sentence parser
known_cities.py     Large US cities for the backup sentence parser
ratelimit.py        In-memory rate limiter
places.json         Saved Austin places, used if SerpApi is down
tests/              pytest suite
deploy/             EC2 setup + update scripts and guide
frontend/app/
  page.tsx                  Solo game
  group/page.tsx            Create / join a party
  group/[roomId]/           Party room: lobby, questions, voting, winner
  components/WalkingCat.tsx The cat mascot (SVG + CSS animation)
```

## Deploying

The live site runs on one AWS EC2 server with Caddy for HTTPS.
- **First-time setup:** see [`deploy/README.md`](deploy/README.md) (one script: `bash deploy/setup.sh yourdomain.tech`).
- **Ship an update:** push to `main`, then on the server run:
  ```bash
  cd ~/FindMyVibe && bash deploy/update.sh
  ```

Every game turn uses your SerpApi and Gemini quota, so share the live link with
judges and teammates rather than posting it publicly.

## License

[MIT](LICENSE)
