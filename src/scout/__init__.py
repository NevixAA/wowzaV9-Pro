"""League scout: collect odds, results and a baseline model for leagues Wowza does not bet yet.

The question it exists to answer, per league: is this market soft enough to beat? Historical odds
cannot be bought back (API-Football /odds is pre-match only), so the evidence has to be collected
forward, starting now. See docs/LEAGUE_SCOUT.md.
"""
