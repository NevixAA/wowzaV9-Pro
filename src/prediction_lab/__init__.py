"""PURE FOOTBALL PREDICTION RESEARCH LAB.

A deliberately separate question from everything else in this estate. Every other study here
asks whether we can beat a price. This one throws the price away and asks the prior question:

    HOW MUCH OF A FOOTBALL MATCH CAN THIS DATA ACTUALLY PREDICT?

Rules that make this lab different, and that the code enforces rather than merely states:

  * EVERY eligible fixture gets a prediction. Not bets, not signals, not threshold-passers.
    Selection on our own betting decisions is what made earlier accuracy numbers meaningless
    (BTTS runs 52.0% across all fixtures and 62.3% on the subset we chose to bet).
  * NO ODDS in the primary experiment. Market information is an ABLATION, added later and
    reported separately, never mixed into the football-only claim.
  * ACCURACY IS REPORTED AGAINST A ROCK. "74% accurate on Over 3.5" is worthless when Under 3.5
    happens 74% of the time. Only the lift over the majority-class baseline is a result.
  * CHRONOLOGICAL ONLY. No random splits anywhere, no threshold chosen on the test period.
  * NOTHING HERE TOUCHES v9. Research code, research outputs, research models. No promotion.
"""
