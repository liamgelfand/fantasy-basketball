"""Command line: python -m fbb <command>"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import sys

from .config import load_config


def _engine():
    from .engine import Engine
    from .espn import LeagueData

    cfg = load_config()
    print("Fetching league data from ESPN...", file=sys.stderr)
    return Engine(LeagueData(cfg))


def _save(cfg, name: str, text: str) -> None:
    cfg.reports_dir.mkdir(exist_ok=True)
    path = cfg.reports_dir / f"{dt.date.today().isoformat()}-{name}.md"
    path.write_text(text, encoding="utf-8")
    print(f"\nSaved to {path}", file=sys.stderr)


def _print_tool(name: str, args: dict) -> None:
    shown = json.dumps(args, default=str) if args else ""
    print(f"  · {name}{' ' + shown if shown else ''}", file=sys.stderr)


def cmd_check(_args) -> None:
    engine = _engine()
    d = engine.data
    elapsed, remaining = d.matchup_periods
    print(f"League:     {d.name} ({d.scoring_type}), season {d.year}")
    print(f"Your team:  {d.my_team.name} [id {d.my_team_id}] {d.my_team.record}")
    print(f"Categories: {', '.join(c.stat + (' (lower wins)' if c.reverse else '') for c in d.categories)}")
    print(f"Starters:   {' '.join(d.lineup_slots)}  | roster spots: {d.roster_size}")
    opp = engine.projection.opponent
    print(f"Matchup:    vs {opp.name if opp else 'none'} | days elapsed {len(elapsed)}, remaining {len(remaining)} "
          f"({d.sp_date(remaining[0]) if remaining else '-'} to {d.sp_date(remaining[-1]) if remaining else '-'})")
    print(f"Free agents loaded: {len(d.free_agents())}")
    print("\nEverything works. If the matchup end date looks wrong, set MATCHUP_END_DATE in .env.")


def cmd_report(args) -> None:
    from .report import build_report

    engine = _engine()
    text = build_report(engine)
    if args.ai:
        from .agent import AI_REPORT_PROMPT, FantasyAgent

        print("Asking Claude for a game plan (this takes a minute)...", file=sys.stderr)
        agent = FantasyAgent(engine)
        plan = agent.ask(AI_REPORT_PROMPT, on_tool=_print_tool)
        text = f"# Game plan (Claude)\n\n{plan}\n\n---\n\n{text}"
    print(text)
    if not args.no_save:
        _save(engine.cfg, "ai-report" if args.ai else "report", text)


def cmd_ask(args) -> None:
    from .agent import FantasyAgent

    agent = FantasyAgent(_engine())
    print(agent.ask(" ".join(args.question), on_tool=_print_tool))


def cmd_chat(_args) -> None:
    from .agent import FantasyAgent

    agent = FantasyAgent(_engine())
    print(f"Chatting about {agent.data.my_team.name}. Type 'exit' to quit.\n")
    while True:
        try:
            q = input("you> ").strip()
        except (EOFError, KeyboardInterrupt):
            break
        if q.lower() in {"exit", "quit", "q"}:
            break
        if q:
            print("\n" + agent.ask(q, on_tool=_print_tool) + "\n")


def cmd_json(args) -> None:
    """Dump structured data (handy for debugging or piping elsewhere)."""
    engine = _engine()
    d = engine.data
    payload = {
        "matchup": engine.projection_summary,
        "roster": lambda: engine.team_summary(d.my_team),
        "free-agents": lambda: [engine.fa_row(r) for r in engine.top_streamers(25)],
        "standings": lambda: [engine.team_summary(t) | {"roster": None} for t in d.standings()],
    }[args.what]()
    print(json.dumps(payload, indent=2, default=str))


def cmd_serve(args) -> None:
    import os
    import threading
    import webbrowser

    import uvicorn

    from .api.app import WEB_DIST

    local = args.host in ("127.0.0.1", "localhost", "::1")
    if not local and "FBB_ALLOWED_HOSTS" not in os.environ:
        # You chose to expose the server on your network (e.g. to use it from your phone).
        os.environ["FBB_ALLOWED_HOSTS"] = "*"
        print("Warning: the API has no login. Anyone on your network can use it (and your Claude key).",
              file=sys.stderr)
    url = f"http://{'localhost' if local or args.host == '0.0.0.0' else args.host}:{args.port}"
    if not (WEB_DIST / "index.html").is_file():
        print("Web client not built yet: run `npm install && npm run build` in web/ (API still available).",
              file=sys.stderr)
    elif not args.no_browser:
        threading.Timer(1.5, webbrowser.open, [url]).start()
    print(f"Fantasy HQ on {url}  (API docs: {url}/api/docs)", file=sys.stderr)
    uvicorn.run("fbb.api:create_app", factory=True, host=args.host, port=args.port, reload=args.reload)


def main(argv: list[str] | None = None) -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")  # emoji in tables on Windows consoles
    parser = argparse.ArgumentParser(prog="fbb", description="ESPN fantasy basketball analyst")
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("check", help="verify credentials and show what was detected").set_defaults(fn=cmd_check)

    p = sub.add_parser("report", help="full matchup / roster / pickup report")
    p.add_argument("--ai", action="store_true", help="add a Claude-written game plan (uses your API key)")
    p.add_argument("--no-save", action="store_true", help="don't write the report to reports/")
    p.set_defaults(fn=cmd_report)

    p = sub.add_parser("ask", help="ask Claude one question about your team")
    p.add_argument("question", nargs="+")
    p.set_defaults(fn=cmd_ask)

    sub.add_parser("chat", help="interactive conversation with Claude about your team").set_defaults(fn=cmd_chat)

    p = sub.add_parser("json", help="dump structured data")
    p.add_argument("what", choices=["matchup", "roster", "free-agents", "standings"])
    p.set_defaults(fn=cmd_json)

    p = sub.add_parser("serve", help="run the Fantasy HQ web app (API + dashboard)")
    p.add_argument("--host", default="127.0.0.1", help="interface to bind (default: local only)")
    p.add_argument("--port", type=int, default=8000)
    p.add_argument("--reload", action="store_true", help="auto-reload on code changes (development)")
    p.add_argument("--no-browser", action="store_true", help="don't open a browser tab")
    p.set_defaults(fn=cmd_serve)

    args = parser.parse_args(argv)
    args.fn(args)


if __name__ == "__main__":
    main()
