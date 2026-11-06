"""A synthetic league that duck-types LeagueData, shared by the offline tests."""
import datetime as dt
import random

from fbb.config import Config
from fbb.espn import Category, PlayerInfo, TeamInfo

CATS = [Category(s, s == "TO") for s in ("PTS", "REB", "AST", "STL", "BLK", "3PM", "FG%", "FT%", "TO")]
SLOTS = ["PG", "SG", "SF", "PF", "C", "G", "F", "UT", "UT", "UT"]
START = dt.date(2026, 10, 26)
POSITIONS = [["PG", "G", "UT"], ["SG", "G", "UT"], ["SF", "F", "UT"], ["PF", "F", "UT"], ["C", "UT"],
             ["PG", "SG", "G", "UT"], ["PF", "C", "F", "UT"]]


def make_player(i: int, rng: random.Random, slot: str = "BE", status: str = "ACTIVE") -> PlayerInfo:
    fga, fta, tpa = rng.uniform(5, 20), rng.uniform(1, 8), rng.uniform(1, 8)
    pg = {
        "PTS": rng.uniform(6, 30), "REB": rng.uniform(2, 12), "AST": rng.uniform(1, 9), "STL": rng.uniform(0.3, 1.8),
        "BLK": rng.uniform(0.1, 2.0), "TO": rng.uniform(0.5, 3.5), "FGA": fga, "FGM": fga * rng.uniform(0.4, 0.58),
        "FTA": fta, "FTM": fta * rng.uniform(0.6, 0.92), "3PA": tpa, "3PM": tpa * rng.uniform(0.3, 0.42),
    }
    pg["FG%"], pg["FT%"] = pg["FGM"] / fga, pg["FTM"] / fta
    pg["FPTS"] = pg["PTS"] + pg["REB"] + 2 * pg["AST"]
    elig = POSITIONS[i % len(POSITIONS)] + ["BE", "IR"]
    return PlayerInfo(id=i, name=f"Player {i}", pro_team="BOS", position=elig[0], eligible_slots=elig,
                      lineup_slot=slot, injury_status=status, expected_return=None, per_game=pg, gp=10,
                      window="season", windows={"season": pg, "last_15": pg},
                      game_days={sp for sp in range(1, 60) if rng.random() < 0.5})


class FakeData:
    """Duck-types the parts of LeagueData that Engine and the report use."""

    def __init__(self):
        rng = random.Random(7)
        self.cfg = Config(league_id=1, year=2027, team_id=1, espn_s2=None, swid=None, model="m", effort="high",
                          stat_window="season")
        self.categories, self.lineup_slots, self.is_points = CATS, SLOTS, False
        self.name, self.scoring_type, self.roster_size = "Test League", "H2H_CATEGORY", 13
        self.today_sp = 7
        self.started = False  # today's first game has tipped
        pid = iter(range(1000))
        self.teams = {}
        for tid in (1, 2, 3, 4):
            roster = [make_player(next(pid), rng, slot=SLOTS[k] if k < 10 else "BE") for k in range(13)]
            self.teams[tid] = TeamInfo(tid, f"Team {tid}", f"T{tid}", 3, 2, 0, tid, 0.0, 1, [], roster)
        self.teams[1].roster[-1].injury_status = "OUT"
        self._fas = [make_player(next(pid), rng) for _ in range(30)]
        self.my_team_id = 1
        self.matchup_periods = ([5, 6], [7, 8, 9, 10, 11])
        self.acquisition_rules = {"matchup_acquisition_limit": 4}

    my_team = property(lambda self: self.teams[1])
    rostered_players = property(lambda self: [p for t in self.teams.values() for p in t.roster])

    def free_agents(self, size=None, position=None):
        return self._fas

    def current_matchup(self):
        return self.teams[2], {"PTS": 200, "REB": 80, "AST": 50, "STL": 15, "BLK": 9, "3PM": 25, "FG%": 0.47,
                               "FT%": 0.79, "TO": 30}, \
            {"PTS": 210, "REB": 70, "AST": 55, "STL": 12, "BLK": 11, "3PM": 22, "FG%": 0.45, "FT%": 0.81, "TO": 28}

    def sp_date(self, sp):
        return START + dt.timedelta(days=sp - self.today_sp)

    def today_started(self):
        return self.started

    def rest_of_season_periods(self):
        return list(range(self.today_sp, 60))

    def owner_of(self, p):
        return next((t for t in self.teams.values() if any(x.id == p.id for x in t.roster)), None)

    def find_player(self, name):
        return next((p for p in self.rostered_players + self._fas if p.name.lower() == name.lower()), None)

    def player_by_id(self, player_id):
        return next((p for p in self.rostered_players + self._fas if p.id == player_id), None)

    def player_news(self, p, limit=5):
        return [{"published": "2026-10-26T18:00:00Z", "headline": f"{p.name} cleared to play", "story": "Good news."}]

    def find_team(self, q):
        return next((t for t in self.teams.values() if t.name.lower() == q.lower()), None)

    def standings(self):
        return list(self.teams.values())

    def recent_activity(self, size=15):
        return [{"date": "2026-10-25 10:00", "team": "Team 2", "action": "FA ADDED", "player": "Player 99"}]


STRONG = {"PTS": 24.0, "REB": 8.0, "AST": 6.0, "STL": 1.4, "BLK": 1.0, "TO": 2.0, "FGA": 17.0, "FGM": 8.5,
          "FTA": 6.0, "FTM": 5.0, "3PA": 7.0, "3PM": 2.8}


def streaming_league(full_roster: bool = False) -> FakeData:
    """My roster has no SF-eligible player, so the SF slot sits empty every day.

    Free agents: "SF Today" (SF, plays only today, sp 7) and "SF Later" (SF, plays sp 8-11).
    Every roster player plays all of sp 7-11. 12 active players leave one roster spot open;
    `full_roster` fills it. The opponent mirrors my first 12 players and the totals so far are tied.
    """
    data = FakeData()
    rng = random.Random(11)
    non_sf = [["PG", "G", "UT"], ["SG", "G", "UT"], ["PF", "F", "UT"], ["C", "UT"]]
    roster = []
    for k in range(13 if full_roster else 12):
        p = make_player(500 + k, rng, slot=SLOTS[k] if k < 10 and SLOTS[k] != "SF" else "BE")
        p.eligible_slots = non_sf[k % 4] + ["BE", "IR"]
        p.position = p.eligible_slots[0]
        p.game_days = set(range(7, 12))
        roster.append(p)
    data.teams[1].roster = roster
    # Tight matchup: the opponent mirrors my roster (same holes) and the totals so far are tied.
    data.teams[2].roster = [PlayerInfo(**{**p.__dict__, "id": p.id + 100, "name": f"Opp {p.id}"}) for p in roster[:12]]
    tied = data.current_matchup()[1]
    data.current_matchup = lambda: (data.teams[2], dict(tied), dict(tied))

    def sf(i: int, name: str, days: set[int]) -> PlayerInfo:
        p = make_player(i, rng)
        p.name, p.eligible_slots, p.position, p.game_days = name, ["SF", "F", "UT", "BE", "IR"], "SF", days
        p.per_game = {**STRONG, "FG%": STRONG["FGM"] / STRONG["FGA"], "FT%": STRONG["FTM"] / STRONG["FTA"]}
        return p

    data._fas = [sf(600, "SF Today", {7}), sf(601, "SF Later", {8, 9, 10, 11})]
    return data
