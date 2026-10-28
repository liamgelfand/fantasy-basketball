"""Claude agent over the league data. Claude calls these tools; we run them locally against the snapshot."""
from __future__ import annotations

import datetime as dt
import json
from dataclasses import asdict
from typing import Callable

import anthropic

from .engine import Engine
from .report import build_report

SYSTEM_PROMPT = """You are a sharp fantasy basketball analyst advising the manager of one team in an ESPN league.

You have tools that read a live snapshot of the league: rosters, the current matchup with a
lineup-aware projection, free agents, player details and news, standings, and a move simulator
that re-projects the matchup after hypothetical adds and drops. Ground every claim in tool output
and say which numbers drove the call. Use web search for news ESPN's feed may lag on: injury
updates, minutes changes, rotation news, return timelines. Mention dates when you cite news.

Nothing you suggest is executed automatically: the manager makes the moves in the ESPN app. So be
concrete: exact player names, which day, which slot, who to drop. Before recommending an add/drop,
run simulate_moves on it. Weigh this week's matchup against rest-of-season value and say which
one a recommendation is for. Respect acquisition limits and punted categories.

Today is {today}. League: {league} ({scoring}). The manager's team: {team}."""


def _json(obj) -> str:
    return json.dumps(obj, default=str, separators=(",", ":"))


class FantasyAgent:
    def __init__(self, engine: Engine, client: anthropic.Anthropic | None = None):
        self.engine = engine
        self.data = engine.data
        self.cfg = engine.cfg
        self.client = client or anthropic.Anthropic()
        self.messages: list[dict] = []
        self.tools, self.handlers = self._build_tools()
        self.system = SYSTEM_PROMPT.format(
            today=dt.date.today().isoformat(),
            league=self.data.name,
            scoring=self.data.scoring_type,
            team=self.data.my_team.name,
        )

    # ---------- tools ----------

    def _resolve_players(self, names: list[str]) -> tuple[list, list[str]]:
        found, missing = [], []
        for n in names:
            p = self.data.find_player(n)
            (found if p else missing).append(p or n)
        return found, missing

    def _build_tools(self) -> tuple[list[dict], dict[str, Callable[..., object]]]:
        e, d = self.engine, self.data
        window_desc = "Stats window: blend (season blended with projection early in the year), season, last_30, last_15, last_7, projected."

        def league_overview():
            return {
                "league": d.name, "scoring_type": d.scoring_type,
                "categories": [asdict(c) for c in d.categories],
                "starting_slots": d.lineup_slots, "roster_spots": d.roster_size,
                "acquisition_rules": d.acquisition_rules,
                "my_team": {"name": d.my_team.name, "record": d.my_team.record, "standing": d.my_team.standing,
                            "acquisitions_this_season": d.my_team.acquisitions},
                "punted_categories": sorted(self.cfg.punt_categories),
                "stat_window_in_use": self.cfg.stat_window,
                "today_scoring_period": d.today_sp, "todays_games_started": d.today_started(),
            }

        def my_roster():
            return {
                "team": e.team_summary(d.my_team),
                "lineup_check_today": e.lineup_check(),
                "weakest_spots": [p.name for p in e.drop_candidates[:4]],
            }

        def matchup_projection():
            return e.projection_summary()

        def team_roster(team: str):
            t = d.find_team(team)
            return e.team_summary(t) if t else {"error": f"No team matching {team!r}",
                                                "teams": [x.name for x in d.teams.values()]}

        def free_agents(position: str | None = None, limit: int = 15, sort: str = "matchup"):
            rows = e.free_agents_at(position.upper(), size=max(limit * 2, 30)) if position else e.free_agent_board
            matchup = lambda r: e.matchup_gain(r["result"])
            key = {"matchup": matchup, "season": lambda r: r["value"],
                   "weighted": lambda r: r["weighted_value"]}.get(sort, matchup)
            return [e.fa_row(r) for r in sorted(rows, key=key, reverse=True)[:limit]]

        def player_details(name: str, include_news: bool = True):
            p = d.find_player(name)
            if not p:
                return {"error": f"No player matching {name!r}"}
            out = e.player_summary(p, detail=True)
            if include_news:
                try:
                    out["news"] = d.player_news(p)
                except Exception as ex:
                    out["news_error"] = str(ex)
            return out

        def simulate_moves(add: list[str] | None = None, drop: list[str] | None = None):
            adds, miss_a = self._resolve_players(add or [])
            drops, miss_d = self._resolve_players(drop or [])
            if miss_a or miss_d:
                return {"error": f"Could not find: {miss_a + miss_d}"}
            mine = {p.id for p in d.my_team.roster}
            bad = [p.name for p in drops if p.id not in mine]
            if bad:
                return {"error": f"Not on your roster: {bad}"}
            taken = [f"{p.name} ({d.owner_of(p).name})" for p in adds if d.owner_of(p)]
            result = asdict(e.simulate(adds, drops))
            if taken:
                result["notes"].append(f"Already rostered elsewhere (trade target, not a pickup): {taken}")
            return result

        def evaluate_trade(give: list[str], receive: list[str]):
            gives, m1 = self._resolve_players(give)
            gets, m2 = self._resolve_players(receive)
            if m1 or m2:
                return {"error": f"Could not find: {m1 + m2}"}
            return e.evaluate_trade(gives, gets)

        def standings():
            return [{"standing": t.standing, "team": t.name, "record": t.record, "points_for": t.points_for}
                    for t in d.standings()]

        def recent_activity(limit: int = 20):
            return d.recent_activity(limit)

        def full_report():
            return build_report(e)

        handlers = {f.__name__: f for f in (league_overview, my_roster, matchup_projection, team_roster, free_agents,
                                            player_details, simulate_moves, evaluate_trade, standings,
                                            recent_activity, full_report)}
        names = {"type": "array", "items": {"type": "string"}}
        schema = lambda props=None, req=None: {"type": "object", "properties": props or {}, "required": req or []}
        tools = [
            {"name": "league_overview", "description": "League settings: categories, roster slots, acquisition limits, my record.", "input_schema": schema()},
            {"name": "my_roster", "description": f"My roster with per-game stats, z-score values, injury status, games left this matchup and rest of season, plus a check of today's lineup. {window_desc}", "input_schema": schema()},
            {"name": "matchup_projection", "description": "Current matchup: live category totals, lineup-aware projected finals, per-category win probabilities, and a day-by-day plan of starts, open slots and benched games for both teams.", "input_schema": schema()},
            {"name": "team_roster", "description": "Another fantasy team's roster and record. Accepts team name, abbreviation, or id.", "input_schema": schema({"team": {"type": "string"}}, ["team"])},
            {"name": "free_agents", "description": "Free agents ranked by sort='matchup' (this matchup's gain after the best drop: projected fantasy points in points leagues, expected categories in category leagues), 'season' (rest-of-season z value), or 'weighted' (value weighted toward swing categories). Optional position filter: PG, SG, SF, PF, C, G, F.",
             "input_schema": schema({"position": {"type": "string"}, "limit": {"type": "integer"},
                                     "sort": {"type": "string", "enum": ["matchup", "season", "weighted"]}})},
            {"name": "player_details", "description": "One player in depth: every stats window (season, last 30/15/7, projected), upcoming game dates, owner, and recent ESPN news.",
             "input_schema": schema({"name": {"type": "string"}, "include_news": {"type": "boolean"}}, ["name"])},
            {"name": "simulate_moves", "description": "Re-project the current matchup after adding and/or dropping players. Returns expected categories won and win probability before and after, per-category changes, and rest-of-season value change.",
             "input_schema": schema({"add": names, "drop": names})},
            {"name": "evaluate_trade", "description": "Evaluate a trade from my side: per-category z-score and per-game changes, rest-of-season games, and the effect on this matchup.",
             "input_schema": schema({"give": names, "receive": names}, ["give", "receive"])},
            {"name": "standings", "description": "League standings.", "input_schema": schema()},
            {"name": "recent_activity", "description": "Recent league adds, drops and trades.", "input_schema": schema({"limit": {"type": "integer"}})},
            {"name": "full_report", "description": "The full deterministic markdown report (matchup, roster, pickups, standings). Good starting point for broad questions.", "input_schema": schema()},
        ]
        if self.cfg.web_search:
            tools.append({"type": "web_search_20260209", "name": "web_search", "max_uses": 6})
        return tools, handlers

    def _run_tool(self, name: str, args: dict) -> tuple[str, bool]:
        try:
            result = self.handlers[name](**args)
            text = result if isinstance(result, str) else _json(result)
            return text, isinstance(result, dict) and "error" in result
        except Exception as ex:  # report tool failures to Claude instead of crashing the loop
            return f"Tool {name} failed: {type(ex).__name__}: {ex}", True

    # ---------- loop ----------

    def ask(self, question: str, on_tool: Callable[[str, dict], None] | None = None, max_turns: int = 25) -> str:
        """Send one user message, run tools until Claude answers, and keep the history for follow-ups."""
        self.messages.append({"role": "user", "content": question})
        for _ in range(max_turns):
            response = self.client.beta.messages.create(
                model=self.cfg.model,
                max_tokens=16000,
                system=self.system,
                tools=self.tools,
                messages=self.messages,
                thinking={"type": "adaptive"},
                output_config={"effort": self.cfg.effort},
                cache_control={"type": "ephemeral"},
                betas=["server-side-fallback-2026-07-01"],
                fallbacks="default",
            )
            self.messages.append({"role": "assistant", "content": response.content})

            if response.stop_reason == "refusal":
                return "Claude declined to answer this request."
            if response.stop_reason == "pause_turn":  # server-side web search still running
                continue
            if response.stop_reason != "tool_use":
                return "\n".join(b.text for b in response.content if b.type == "text").strip()

            results = []
            for block in response.content:
                if block.type != "tool_use":
                    continue
                if on_tool:
                    on_tool(block.name, block.input)
                text, is_error = self._run_tool(block.name, dict(block.input or {}))
                results.append({"type": "tool_result", "tool_use_id": block.id, "content": text, "is_error": is_error})
            self.messages.append({"role": "user", "content": results})
        return "Stopped: too many tool rounds without a final answer."


AI_REPORT_PROMPT = """Write my game plan for this matchup and the week ahead.

Start from full_report, then dig in where it matters: check news (and the web) for any injured
or questionable players on my roster, my opponent's roster, and the top pickup candidates;
simulate the adds and drops you're considering; check if any trade target fits my category needs.

Output markdown with these sections:
1. **Bottom line**: 2-3 sentences on where the matchup stands and the single most important move.
2. **Moves to make**: a numbered list of exact actions (add/drop/lineup/IR) with the day and reason.
3. **Category strategy**: which categories to chase, protect, or concede this week, and why.
4. **Injury & news watch**: what to monitor and when to re-check.
5. **Longer-term**: roster construction, sell-high/buy-low, trade ideas.
"""
