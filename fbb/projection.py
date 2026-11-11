"""Per-game projections from ESPN's stat windows: a long-term "true talent" estimate and a short-term one.

Pure: takes per-game averages by window (season, last_30, last_15, last_7, projected) plus games
played, returns per-game stat dicts in the same shape. No ESPN or league access, so it's testable offline.

The model, the way a careful manager reads a stat line:
- ESPN's preseason projection is a prior worth only PRIOR_GAMES games; season-to-date is the main evidence.
- Production = minutes x per-minute rate. Minutes carry the role, so a recent window only gets extra
  weight when its minutes differ meaningfully from the season's (a role change: promoted to starter,
  a teammate hurt, benched). Then the new minutes drive the projection and the per-minute rates move a little.
- A hot or cold stretch at the same minutes is mostly noise: the long-term estimate ignores it, the
  short-term one leans on it lightly for volume, and shooting percentages are always regressed toward
  the projection by attempts (makes and attempts are blended, never percentages).
"""
from __future__ import annotations

from dataclasses import dataclass, field

# ESPN's preseason projection counts as this many games of evidence: prior weight = PRIOR_GAMES / (PRIOR_GAMES + gp)
# -> 1 GP 80%, 4 GP 50%, 10 GP 29%, 15 GP 21%, 30 GP 12%. (The old blend used 10: still 50% at 10 GP.)
PRIOR_GAMES = 4.0
# A recent window signals a role change when its minutes differ from the season's by at least this many
# minutes and this fraction, over at least ROLE_MIN_GAMES games.
ROLE_MIN_DELTA = 4.0
ROLE_MIN_FRACTION = 0.15
ROLE_MIN_GAMES = 2
ROLE_WINDOWS = ("last_7", "last_15")  # shortest first: the most current role
# Shooting percentages: the projection's percentage is worth this many attempts. Percentages take a few
# hundred attempts to settle, so a hot month barely moves them.
SHOT_PRIOR_ATTEMPTS = {"FG": 100.0, "FT": 50.0, "3P": 100.0}
# (made, attempts, kind, points per make beyond what the other rows count): PTS = 2 FGM + 3PM + FTM
SHOTS = (("FGM", "FGA", "FG", 2.0), ("FTM", "FTA", "FT", 1.0), ("3PM", "3PA", "3P", 1.0))
# Stats that are ratios or per-game flags: recomputed or averaged, never scaled by minutes.
RATIOS = {"FG%", "FT%", "3PT%", "AFG%", "A/TO", "STR", "PPM", "FTR", "GP", "GS", "MIN", "MPG"}
WINDOW_LABELS = {"last_7": "last 7 days", "last_15": "last 15 days", "last_30": "last 30 days",
                 "season": "season", "projected": "preseason projection"}


@dataclass(frozen=True)
class Horizon:
    """How much a recent window counts, in games of evidence per game it contains."""
    role_minutes: float  # minutes, when the role changed
    role_rates: float  # per-minute rates, when the role changed
    base_cap: float  # after a role change, the old evidence (prior + season) counts as at most this many games
    form_minutes: float  # minutes, no role change
    form_rates: float  # per-minute volume rates, no role change (never shooting percentages)


# Rest of season: follow a real role change, ignore streaks.
LONG = Horizon(role_minutes=3.0, role_rates=0.5, base_cap=10.0, form_minutes=0.0, form_rates=0.0)
# Next ~2 weeks: the current role and form matter more; the old role fades faster.
SHORT = Horizon(role_minutes=6.0, role_rates=1.0, base_cap=6.0, form_minutes=1.0, form_rates=0.5)


@dataclass
class Estimate:
    per_game: dict[str, float]
    weights: dict[str, float] = field(default_factory=dict)  # share of each input window in the projection
    minutes: float = 0.0  # projected minutes per game (0 when ESPN gave none)
    season_minutes: float = 0.0
    recent_window: str | None = None  # the recent window used (role change or form), if any
    recent_minutes: float = 0.0
    role_change: float = 0.0  # recent minus season minutes when a role change was detected, else 0
    note: str = ""

    @property
    def prior_weight(self) -> float:
        return self.weights.get("projected", 0.0)


def _role_shift(recent_min: float, season_min: float) -> float:
    """Recent minus season minutes when the gap is big enough to call a role change, else 0."""
    shift = recent_min - season_min
    if abs(shift) >= ROLE_MIN_DELTA and abs(shift) >= ROLE_MIN_FRACTION * max(season_min, 1.0):
        return shift
    return 0.0


def _recent(windows: dict, gps: dict, season_min: float) -> tuple[str | None, float]:
    """(recent window, role shift). A role change needs the current (shortest) window to show it; the
    longest window agreeing with it is used, for the most games of the new role. Otherwise the steadiest
    usable window is returned for form, with shift 0."""
    usable = [w for w in ROLE_WINDOWS if gps.get(w, 0) >= ROLE_MIN_GAMES and windows.get(w, {}).get("MIN")]
    if not usable:
        return None, 0.0
    current = _role_shift(windows[usable[0]]["MIN"], season_min)
    if current:
        agree = [w for w in usable if _role_shift(windows[w]["MIN"], season_min) * current > 0]
        return agree[-1], _role_shift(windows[agree[-1]]["MIN"], season_min)
    return usable[-1], 0.0


def _avg(sources: list[tuple[dict, float]], key: str, per_min: bool) -> float | None:
    num = den = 0.0
    for stats, w in sources:
        if w <= 0 or key not in stats or (key == "FPTS" and not stats[key]):
            continue  # FPTS is 0 when ESPN sent no fantasy points for the window: missing, not zero
        v = float(stats[key] or 0.0)
        if per_min:
            v /= stats["MIN"]
        num += w * v
        den += w
    return num / den if den else None


def estimate(windows: dict[str, dict[str, float]], gps: dict[str, float], horizon: Horizon = LONG) -> Estimate:
    """Per-game projection for one horizon from the stat windows (missing windows are fine)."""
    season, prior = windows.get("season") or {}, windows.get("projected") or {}
    gp = float(gps.get("season", 0.0)) if season else 0.0
    if not season and not prior:
        for w in ("last_30", "last_15", "last_7"):
            if windows.get(w):
                return Estimate(dict(windows[w]), {w: 1.0}, note=f"Only the {WINDOW_LABELS[w]} window is available.")
        return Estimate({}, note="No stats available.")

    w_prior = PRIOR_GAMES if prior else 0.0
    w_season = gp if season and gp > 0 else (0.0 if prior else 1.0)
    base = [(prior, w_prior), (season, w_season)]
    by_minutes = all(s.get("MIN", 0) > 0 for s, w in base if w > 0)
    season_min = float(season.get("MIN", 0.0)) if season else 0.0

    recent, shift = _recent(windows, gps, season_min) if by_minutes and w_season and season_min else (None, 0.0)
    gp_recent = float(gps.get(recent, 0.0)) if recent else 0.0
    if shift:
        scale = min(1.0, horizon.base_cap / (w_prior + w_season))
        w_min = [(prior, w_prior * scale), (season, w_season * scale), (windows[recent], gp_recent * horizon.role_minutes)]
        w_rate = [*base, (windows[recent], gp_recent * horizon.role_rates)]
    elif recent:
        w_min = [*base, (windows[recent], gp_recent * horizon.form_minutes)]
        w_rate = [*base, (windows[recent], gp_recent * horizon.form_rates)]
    else:  # includes windows without minutes: no way to tell a role change from a streak, so no recency
        w_min = w_rate = base

    minutes = _avg(w_min, "MIN", False) if by_minutes else 0.0
    out: dict[str, float] = {}
    keys = set().union(*(s for s, w in w_rate if w > 0))
    for k in keys:
        if k in RATIOS:
            v = _avg(w_rate, k, False)
        elif by_minutes:
            rate = _avg(w_rate, k, True)
            v = rate * minutes if rate is not None else None
        else:
            v = _avg(w_rate, k, False)
        if v is not None:
            out[k] = v
    if by_minutes:
        out["MIN"] = minutes

    # Shooting: regress the percentage toward the projection by attempts; volume (attempts) stays as blended.
    for made, att, kind, points in SHOTS:
        if not out.get(att):
            continue
        season_att = float(season.get(att, 0.0)) * gp
        season_made = float(season.get(made, 0.0)) * gp
        if prior.get(att):
            k = SHOT_PRIOR_ATTEMPTS[kind]
            rate = (k * prior.get(made, 0.0) / prior[att] + season_made) / (k + season_att)
        elif season_att:
            rate = season_made / season_att
        else:
            rate = out.get(made, 0.0) / out[att]
        new_made = out[att] * rate
        if "PTS" in out:
            out["PTS"] += points * (new_made - out.get(made, 0.0))
        out[made] = new_made
    _recompute_ratios(out)

    w_total = sum(w for _, w in w_min)
    names = {id(prior): "projected", id(season): "season"}
    if recent:
        names[id(windows[recent])] = recent
    weights = {names[id(s)]: round(w / w_total, 3) for s, w in w_min if w > 0}
    est = Estimate(out, weights, minutes=minutes or 0.0, season_minutes=season_min, recent_window=recent,
                   recent_minutes=float(windows[recent]["MIN"]) if recent else 0.0, role_change=shift)
    est.note = _note(est, gp)
    return est


def _recompute_ratios(out: dict[str, float]) -> None:
    def ratio(key: str, num: float, den: float) -> None:
        if key in out and den:
            out[key] = num / den
    ratio("FG%", out.get("FGM", 0.0), out.get("FGA", 0.0))
    ratio("FT%", out.get("FTM", 0.0), out.get("FTA", 0.0))
    ratio("3PT%", out.get("3PM", 0.0), out.get("3PA", 0.0))
    ratio("AFG%", out.get("FGM", 0.0) + 0.5 * out.get("3PM", 0.0), out.get("FGA", 0.0))
    ratio("A/TO", out.get("AST", 0.0), out.get("TO", 0.0))
    ratio("STR", out.get("STL", 0.0), out.get("TO", 0.0))
    ratio("PPM", out.get("PTS", 0.0), out.get("MIN", 0.0))
    ratio("FTR", out.get("FTA", 0.0), out.get("FGA", 0.0))


def _note(est: Estimate, gp: float) -> str:
    prior = est.prior_weight
    if est.role_change:
        label = WINDOW_LABELS.get(est.recent_window or "", est.recent_window)
        way = "up" if est.role_change > 0 else "down"
        return (f"Minutes {way}: {est.recent_minutes:.1f} over the {label} vs {est.season_minutes:.1f} on the season. "
                f"Projected at {est.minutes:.1f} min for the new role.")
    if not gp:
        return "No games yet: ESPN's preseason projection."
    if prior >= 0.4:
        return f"Small sample ({gp:.0f} GP): {prior:.0%} preseason projection, the rest season stats."
    tail = f", {prior:.0%} preseason projection" if prior else ""
    return f"Season stats ({gp:.0f} GP) drive it{tail}; streaks without a minutes change are treated as noise."


def project(windows: dict[str, dict[str, float]], gps: dict[str, float]) -> tuple[Estimate, Estimate]:
    """(long-term, short-term) estimates."""
    return estimate(windows, gps, LONG), estimate(windows, gps, SHORT)
