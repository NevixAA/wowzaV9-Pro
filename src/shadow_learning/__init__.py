"""Shadow learning: which data actually makes Wowza better at predicting future football?

The laboratory is already built. This package uses it.

The architecture audit established that Wowza owns roughly 23,000 completed fixtures its models
never train on, and then established something less comfortable: adding them did not measurably
improve out-of-sample prediction. That is the starting point, not the conclusion. The question
here is which observations earn their place, and whether repeated retraining on accumulating
experience actually makes the system better at football that has not happened yet.

Everything is SHADOW. v9 stays the production champion throughout, nothing here is promoted, and
no production training path is repointed.
"""
