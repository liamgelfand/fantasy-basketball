# fbb: project notes for Claude Code

Python 3.11, venv at `.venv` (`.\.venv\Scripts\python`). Run `python -m pytest` after changes.
Web client in `web/` (Node 20+): run `npm run typecheck && npm run lint && npm test` there after UI changes.

## Layout
- `fbb/espn.py`: the only module that touches `espn_api`. Converts to `PlayerInfo`/`TeamInfo` dataclasses.
- `fbb/analysis.py`: pure math (z-score valuation, daily lineup matching, matchup projection, move simulation). No I/O.
- `fbb/engine.py`: combines data + analysis (FA board, drop candidates, lineup check, trade eval, JSON summaries).
- `fbb/report.py`: deterministic markdown report. `fbb/agent.py`: Claude tool loop over Engine methods.
- `fbb/api/`: FastAPI. Routes stay thin; Engine -> JSON mapping lives in `presenters.py`, the contract in `schemas.py`.
- `web/`: React + TS (Mantine, TanStack Query). `src/api/types.ts` mirrors `schemas.py`: change both together.
- `tests/fakes.py`: `FakeData` duck-types LeagueData; extend it when Engine needs new data. `tests/test_api.py` covers HTTP.

## Conventions
- Keep ESPN read-only. Don't add write/transaction calls.
- New agent capabilities = a function in `FantasyAgent._build_tools` + a schema entry.
- New UI data = Engine method -> presenter + schema -> route -> `types.ts` + query hook -> feature page.
- Secrets live in `.env` (gitignored). Never print or log ESPN_S2/SWID/API keys.

## My league (fill in)
- Scoring: (e.g. 9-cat H2H)
- Strategy / punts: 
- Preferences: 
