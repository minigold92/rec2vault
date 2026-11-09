import os

# Tests must not pick up the installed pipeline's ~/rec/settings.env (e.g. its REC_SINCE cutoff).
# conftest is imported before the test modules import rec.config.
os.environ["REC_SETTINGS"] = os.devnull
