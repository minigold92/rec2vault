import os
import tempfile

# Never read an installed user's settings or data, even during module import.
_ROOT = tempfile.TemporaryDirectory(prefix='quietclerk-tests-')
for _key in list(os.environ):
    if _key.startswith('QC_'):
        del os.environ[_key]
os.environ['QC_ROOT'] = _ROOT.name
os.environ['QC_SETTINGS'] = os.devnull
os.environ['QC_SINCE'] = '1970-01-01 00:00'
