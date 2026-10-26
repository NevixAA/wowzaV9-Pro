"""STANDARD FORMAT REPAIR research programme (owner brief 2026-10-26, part B). Research only.

Question: can a Standard-league model add information AFTER conditioning on the market?

    python -m src.studies.standard_repair build     # frame: v9 features + pre-match prices + market probs
    python -m src.studies.standard_repair run       # chronological benchmark -> output/standard_repair/
    python -m src.studies.standard_repair forward   # served v9 vs market on Pro's first-sight rows

Modules: data (frame + de-vig + market inversion), candidates (the arms), evaluate (walk-forward,
metrics, block bootstrap, BH-FDR), forward (prospective first-sight design), v9_probe (v9's own
trainer, run inside a v9 checkout). Nothing here writes into v9 or changes production.
"""
