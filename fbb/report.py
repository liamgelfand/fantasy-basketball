"""Deterministic markdown report: matchup, lineup, roster, pickups, league context."""
from __future__ import annotations

import datetime as dt

from .analysis import stat
from .engine import Engine


def _pct(x: float) -> str:
    return ">99%" if x > 0.995 else "<1%" if x < 0.005 else f"{100 * x:.0f}%"


def _fmt(cat: str, v: float) -> str:
    return f"{v:.3f}" if "%" in cat or cat == "A/TO" else f"{v:.1f}" if abs(v) < 100 else f"{v:.0f}"


def _table(headers: list[str], rows: list[list]) -> str:
    out = ["| " + " | ".join(headers) + " |", "|" + "---|" * len(headers)]
    out += ["| " + " | ".join(str(c) for c in r) + " |" for r in rows]
    return "\n".join(out)


def build_report(engine: Engine) -> str:
    d = engine.data
    me = d.my_team
    proj = engine.projection
    lines: list[str] = []
    add = lines.append

    add(f"# {me.name}: Fantasy Report ({dt.date.today():%a %b %d, %Y})")
    add(f"**League:** {d.name} · {d.scoring_type.replace('_', ' ').title()} · "
        f"**Record:** {me.record} (#{me.standing}) · **Stat window:** {engine.cfg.stat_window}"
        + (f" · **Punting:** {', '.join(sorted(engine.cfg.punt_categories))}" if engine.cfg.punt_categories else ""))
    add("")

    # ---- action items
    actions = _action_items(engine)
    add("## Do this now")
    add("\n".join(f"{i}. {a}" for i, a in enumerate(actions, 1)) if actions else "Nothing urgent. Your lineup and roster look set.")
    add("")

    # ---- matchup
    if proj.opponent:
        opp = proj.opponent
        days = [d.sp_date(s) for s in proj.elapsed + proj.remaining]
        span = f"{days[0]:%b %d} to {days[-1]:%b %d}" if days else "?"
        add(f"## Matchup vs {opp.name} ({opp.record}) · {span}")
        add(f"**Projected categories won:** {proj.expected_wins:.1f} / {len(proj.categories)} · "
            f"**Win probability:** {_pct(proj.win_matchup_prob)} · "
            f"**Starts left:** you {proj.mine.remaining_games:.0f}, them {proj.theirs.remaining_games:.0f}")
        add("")
        rows = []
        for c in proj.categories:
            lean = "✅" if c.win_prob >= 0.7 else "❌" if c.win_prob <= 0.3 else "⚖️"
            rows.append([c.stat, _fmt(c.stat, c.mine_now), _fmt(c.stat, c.theirs_now),
                         _fmt(c.stat, c.mine_final), _fmt(c.stat, c.theirs_final), f"{lean} {_pct(c.win_prob)}"])
        add(_table(["Cat", "You now", "Opp now", "You proj", "Opp proj", "Win %"], rows))
        add("")
        swing = [c.stat for c in proj.categories if 0.3 < c.win_prob < 0.7]
        if swing:
            add(f"**Swing categories:** {', '.join(swing)}. Moves should target these.")
            add("")

        add("### Remaining days")
        theirs = {x.sp: x for x in proj.theirs.days}
        rows = []
        for day in proj.mine.days:
            o = theirs.get(day.sp)
            rows.append([f"{day.date:%a %m/%d}", day.playing, len(day.started), day.open_slots,
                         ", ".join(day.benched) or "-", len(o.started) if o else "-"])
        add(_table(["Day", "Your games", "Your starts", "Open slots", "Benched (no slot)", "Opp starts"], rows))
        add("")
    else:
        add("## Matchup\nNo active matchup found (bye week or off-season).\n")

    # ---- roster
    add("## Your roster")
    stats = engine.display_stats()
    rows = []
    for p in sorted(me.roster, key=engine.value, reverse=True):
        trend = ""
        l15, season = p.windows.get("last_15"), p.windows.get("season")
        if l15 and season:
            delta = engine.valuer.total(_with(p, l15)) - engine.valuer.total(_with(p, season))
            trend = "🔥" if delta > 1.5 else "🧊" if delta < -1.5 else ""
        status = "" if p.injury_status in ("ACTIVE", "", None) else p.injury_status
        rows.append([p.lineup_slot, f"{p.name} {trend}".strip(), p.pro_team, status, engine.games_left(p),
                     f"{engine.value(p):+.1f}"] + [_fmt(s, stat(p, s)) for s in stats])
    add(_table(["Slot", "Player", "Tm", "Status", "G left", "Value"] + stats, rows))
    add("\n_Value = sum of per-game z-scores vs all rostered players (punted cats excluded). 🔥/🧊 = last 15 days well above/below season._\n")

    # ---- pickups
    add("## Best pickups for this matchup")
    rows = []
    gain_label = "Proj FPTS +" if d.is_points else "Exp cats +"
    for r in engine.top_streamers(8):
        res = r["result"]
        gain = engine.matchup_gain(res)
        if gain <= (1.0 if d.is_points else 0.01):
            continue
        p = r["player"]
        rows.append([p.name, p.pro_team, "/".join(_pos(p)), p.injury_status if p.injury_status != "ACTIVE" else "",
                     r["games_left"], f"+{gain:.1f}" if d.is_points else f"+{gain:.2f}", _pct(res.win_prob_after),
                     r["drop"].name if r["drop"] else "(open spot)", f"{r['value']:+.1f}"])
    add(_table(["Player", "Tm", "Pos", "Status", "G left", gain_label, "Win % after", "Drop", "Season value"], rows)
        if rows else "No free agent improves this matchup.")
    add("")

    add("## Best long-term adds")
    rows = []
    for r in engine.top_season_adds(8):
        p = r["player"]
        rows.append([p.name, p.pro_team, "/".join(_pos(p)), p.injury_status if p.injury_status != "ACTIVE" else "",
                     f"{r['value']:+.1f}", f"{r['value_over_worst']:+.1f}", engine.ros_games(p)])
    add(_table(["Player", "Tm", "Pos", "Status", "Value", "vs your worst", "ROS games"], rows))
    add("")
    worst = engine.drop_candidates[:3]
    if worst:
        add("**Weakest roster spots:** " + ", ".join(f"{p.name} ({engine.value(p):+.1f})" for p in worst))
        add("")

    # ---- league context
    add("## Standings")
    rows = [[t.standing, t.name + (" ⬅️" if t.id == me.id else ""), t.record] for t in d.standings()]
    add(_table(["#", "Team", "Record"], rows))
    add("")

    try:
        activity = d.recent_activity(12)
    except Exception as e:  # activity needs auth in private leagues; don't sink the whole report
        activity = []
        add(f"_Recent activity unavailable: {e}_\n")
    if activity:
        add("## Recent league activity")
        add(_table(["When", "Team", "Action", "Player"], [[a["date"], a["team"], a["action"], a["player"]] for a in activity]))
        add("")

    rules = d.acquisition_rules
    if rules.get("matchup_acquisition_limit"):
        add(f"_Acquisitions: limit {rules['matchup_acquisition_limit']} per matchup; you have made {me.acquisitions} this season._")
    return "\n".join(lines)


def _with(p, window_stats):
    from .espn import PlayerInfo
    return PlayerInfo(**{**p.__dict__, "per_game": window_stats})


def _pos(p) -> list[str]:
    return [s for s in p.eligible_slots if s in ("PG", "SG", "SF", "PF", "C")]


def _action_items(engine: Engine) -> list[str]:
    items = []
    lc = engine.lineup_check()
    if lc["start"] and not lc["games_started"]:
        items.append(f"Today's lineup: start **{', '.join(lc['start'])}**"
                     + (f" in place of {', '.join(lc['bench'])}." if lc["bench"] else " (open starting slots)."))
    items += [f"Move **{n}** to IR to free a roster spot (if your IR slot is open)." for n in lc["ir_candidates"]]

    best = engine.top_streamers(1)
    is_points = engine.data.is_points
    if best and engine.matchup_gain(best[0]["result"]) >= (15.0 if is_points else 0.25):
        r = best[0]
        gain = engine.matchup_gain(r["result"])
        drop = f"drop **{r['drop'].name}**" if r["drop"] else "use your open roster spot"
        items.append(f"Add **{r['player'].name}** ({r['games_left']} games left), {drop}: "
                     + (f"+{gain:.0f} projected fantasy points" if is_points else f"+{gain:.2f} expected categories")
                     + f", win probability {_pct(r['result'].win_prob_before)} → {_pct(r['result'].win_prob_after)}.")
    season = engine.top_season_adds(1)
    if season and season[0]["value_over_worst"] >= 1.5 and (not best or season[0]["player"].id != best[0]["player"].id):
        r = season[0]
        items.append(f"Long-term upgrade: **{r['player'].name}** is worth {r['value_over_worst']:+.1f} z over "
                     f"**{engine.drop_candidates[0].name}**.")
    return items
