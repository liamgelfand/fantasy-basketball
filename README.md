# fbb: ESPN fantasy basketball analyst

Pulls your ESPN league (rosters, live matchup, free agents, schedules, injuries, news, standings,
activity), projects your matchup lineup-aware, ranks pickups by how much they actually move
the matchup, and optionally lets Claude reason over all of it.

ESPN has no official API and no supported way to make roster moves, so this tool is
**read-only**: it tells you exactly what to do and you make the move in the ESPN app.

## Setup

```powershell
python -m venv .venv
.\.venv\Scripts\activate
pip install -r requirements.txt
copy .env.example .env    # then fill it in
python -m fbb check       # verifies everything and shows what it detected
```

**ESPN cookies (private leagues):** log into fantasy.espn.com in Chrome, press F12 →
Application → Cookies → `https://fantasy.espn.com`, copy `espn_s2` and `SWID` into `.env`.
They last months; if requests start failing with 401, grab fresh ones.

## Desktop app (recommended)

One-time setup (Windows, needs Node.js 20+ for the web client build):

```powershell
.\.venv\Scripts\python -m fbb desktop --install-shortcuts   # adds Desktop + Start menu shortcuts
```

Then open **Fantasy HQ** from the desktop or the Start menu. It runs in its own window (Edge WebView2),
with no console and no browser tab:

- It rebuilds the web client on launch whenever anything in `web/` changed, so it's never stale.
- Only one copy runs: opening it again brings the existing window to the front.
- Closing the window stops the server.
- It serves on `127.0.0.1:8765`, so `python -m fbb serve` on :8000 can run alongside it.
- If it can't start (missing `.env` value, build error), the window says why. Logs are in
  `.fbb/logs/desktop.log`.

`python -m fbb desktop` launches it from a terminal, and `--remove-shortcuts` undoes the setup.

## Web app (browser)

Double-click **`Fantasy HQ.bat`** (it builds the web client on first run), or:

```powershell
cd web; npm install; npm run build; cd ..
python -m fbb serve            # http://localhost:8000  (API docs at /api/docs)
```

Pages: Matchup, Roster, Free agents, Simulator, Trades, League, Ask Claude (chat), and Report.
Click any player name for a card with every stat window, upcoming games, and ESPN news.
ESPN data is cached for 10 minutes; use the refresh button in the header for the latest.

Chats are saved (in your browser and in `.fbb/chats/`, gitignored), so they survive reloads and
server restarts. A chat always answers from the data the pages show: change the stat window or
refresh and the next answer uses the new snapshot, with the conversation intact. **Stop** cancels
Claude on the server too, so an abandoned question doesn't keep spending tokens.

The server only answers on `localhost`. To use it from your phone, run
`python -m fbb serve --host 0.0.0.0` (there is no login, so only do this on a network you trust).

### Architecture

```
fbb/                 Python package (domain + API)
  espn.py            ESPN adapter -> PlayerInfo/TeamInfo dataclasses (only module touching espn_api)
  analysis.py        pure math: valuation, lineups, projection, simulation
  engine.py          use cases combining data + analysis
  agent.py           Claude tool loop over Engine methods
  desktop.py         desktop window launcher (pywebview), shortcuts, auto-rebuild
  api/               FastAPI layer
    app.py           app factory; serves /api and the built client
    routes/          thin HTTP handlers (league, players, moves, assistant)
    schemas.py       Pydantic request/response contract
    presenters.py    Engine -> schema mapping (pure)
    services.py      snapshot cache per (stat window, punts), chat sessions + on-disk store
    streaming.py     server-sent events for Claude tool progress
web/                 React + TypeScript (Vite, Mantine UI, TanStack Query, React Router)
  src/api/           typed client, endpoints, query hooks (types mirror schemas.py)
  src/features/      one folder per page
  src/components/    shared UI (DataTable, StatCard, layout, ...)
```

### Development

```powershell
python -m fbb serve --reload --no-browser   # API on :8000
cd web; npm run dev                          # UI on :5173 with hot reload, proxies /api
```

Checks (CI runs all of them on every push): `ruff check .` and `python -m pytest` for the backend;
`npm run typecheck`, `npm run lint`, `npm test` in `web/`.

## Commands

| Command | What it does | Uses Claude |
|---|---|---|
| `python -m fbb check` | Validate config, show categories, slots, matchup dates | no |
| `python -m fbb report` | Full report, saved to `reports/` | no |
| `python -m fbb report --ai` | Report + Claude's game plan (checks news and the web, simulates moves) | yes |
| `python -m fbb ask "should I drop X for Y?"` | One question, answered with tool calls | yes |
| `python -m fbb chat` | Conversation with follow-ups | yes |
| `python -m fbb json matchup` | Raw structured data (`matchup`, `roster`, `free-agents`, `moves`, `standings`) | no |
| `python -m fbb desktop` | Desktop app window (`--install-shortcuts` / `--remove-shortcuts`) | chat only |

## How the numbers work

- **Player value**: per-game z-scores vs every rostered player in your league. FG%/FT% use
  impact (pct above league average × attempts), so volume matters. TO counts negatively.
  Punted categories (`PUNT_CATEGORIES`) are excluded.
- **Stat window** (`STAT_WINDOW`): `model` (default, `fbb/projection.py`) estimates each player's
  per-game production as minutes × per-minute rate. ESPN's preseason projection is a prior worth
  4 games (29% at 10 GP, 21% at 15 GP); season-to-date stats are the main evidence. A recent window
  (last 7/15 days) only gets extra weight when its minutes differ from the season's by 4+ minutes
  and 15%+ (a role change), so a new starter's projection moves and a hot shooting week doesn't.
  Shooting percentages are always regressed toward the projection by attempts. It produces a
  long-term line (player value) and a short-term line (next ~2 weeks: leans harder on the current
  role and lightly on form) used for this matchup's projection. `blend`, `season`, `last_*` and
  `projected` use one ESPN window as-is.
- **Horizons**: *next 2 weeks* and *rest of season* values scale per-game value above replacement
  level (the 5th-best free agent) by the games a player is expected to play: the schedule times
  injury availability, using ESPN's return date (no date: OUT is assumed to last ~2 weeks,
  day-to-day ~3 days). A player out six weeks loses most of their ROS value; one back in days doesn't.
- **Matchup projection**: for each remaining day it builds your best *legal* lineup (positional
  slot matching, highest value first), so benched games from a full roster don't count.
  Injury status discounts availability (OUT 0%, DTD 70%, …). Totals add to ESPN's live stats.
  Win probability per category uses a normal approximation of the final margin.
- **Pickup ranking**: each free agent is simulated on their next game day (so the drop keeps
  any games before it) against your weakest four roster spots (by combined short- and long-term
  value) plus anyone flagged as long-injured or losing minutes. A swap scores this matchup's
  change in expected categories won, plus the change in value beyond it: half a week per z of
  rest-of-season value and a quarter week per z of next-2-weeks value (1 z-week ≈ 0.15
  categories; in points leagues 3.5 games × the FPTS spread). Each pickup is labeled a
  *streamer* (helps this week only), a *stash* (long-term value, little now) or both, with the
  reasons (minutes trend, injury timeline, schedule). A separate list ranks rest-of-season value.
- **Add/drop plan**: a dated sequence of moves, built day by day. Each day it picks the best
  free agent who plays that day (into an open roster spot, else for one of your weakest players
  or a streamer added earlier in the plan), applies it, and searches again on the updated roster.
  So an empty slot today is filled first (no drop if you have a spot), then tomorrow's move is
  planned around it; a streamer dropped later still counts for the games in between. Today is
  skipped once its games tip. If your league has a weekly add limit, the plan is capped to the
  adds you have left: the limit comes from your league settings and this week's adds are counted
  from ESPN's activity feed, so there's nothing to enter. It keeps the fewest adds that capture
  most of the gain and says when the cap cut moves.

## Claude settings

The assistant runs on your Claude plan (Pro or Max) through the
[Claude Agent SDK](https://code.claude.com/docs/en/agent-sdk/overview): install
[Claude Code](https://code.claude.com) and log in (`claude`, then `/login`). No API key is used,
and any `ANTHROPIC_API_KEY` in the environment is ignored so it can't bill API credits. Usage
counts toward your plan's limits. This is meant for personal use; Anthropic does not allow
offering claude.ai login in products for other people.

Defaults: `claude-opus-5-5`, effort `high`, web search on. For lighter runs that use less of
your plan, set `CLAUDE_MODEL=claude-sonnet-5-5` or `CLAUDE_EFFORT=medium`.

## Known limits

- Matchup end date is read from ESPN when listed, otherwise assumed to be the next
  `MATCHUP_END_WEEKDAY` (Sunday). Longer matchups (season opener, All-Star week): set
  `MATCHUP_END_DATE`.
- Today counts as already played once the first game tips (ESPN's live totals include it).
- Free agents are the top `FREE_AGENT_POOL` by % owned; the agent can search by position for more.
- Adds used this week are your FA adds and waiver claims in ESPN's activity feed since the first
  tip of the day before the matchup starts (later adds take effect in the new matchup), or local
  midnight of its first day if there were no games the day before. If the feed can't be read, the
  plan isn't capped and says so.
- Without a league add limit, the plan shows at most about one add per day left.

## Tests

`python -m pytest`: offline tests on a synthetic league, including the HTTP API (no ESPN or Claude calls).
`npm test` in `web/`: component and client tests.
