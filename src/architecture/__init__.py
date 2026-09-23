"""Data-lineage and canonical-architecture audit.

PHASE A ONLY, BY DESIGN. Everything in this package reads. Nothing here writes into v9, changes
a threshold, retrains a model, or moves a file. The output is measurement: what data exists,
who produces it, who consumes it, and -- the question that matters -- how much of what we have
collected never reaches the thing that learns.

The order is deliberate and is the opposite of how this kind of work usually goes. Architecture
proposals are cheap and unfalsifiable; a count of stranded fixtures is neither. So the stranded
count comes first and the design is written afterwards, against it.
"""
