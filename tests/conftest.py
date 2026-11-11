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

# Explicit opt-in for exercising existing intake security tests with the app's
# minimal media tools. Fixture synthesis still uses the developer PATH tools.
if _app_tools := os.environ.get('QUIETCLERK_TEST_APP_TOOLS'):
    from pathlib import Path
    _tools = Path(_app_tools)
    if not _tools.is_absolute() or not all((_tools / name).is_file() for name in ('ffmpeg', 'ffprobe')):
        raise RuntimeError('QUIETCLERK_TEST_APP_TOOLS must name an absolute prepared tool directory')
    os.environ['QC_FFMPEG'] = str(_tools / 'ffmpeg')
    os.environ['QC_FFPROBE'] = str(_tools / 'ffprobe')
