"""The app may request the setup wizard, never an arbitrary redirect target."""
import json
from pathlib import Path
import subprocess

import pytest


@pytest.mark.parametrize('next_value,expected', [('setup', '/setup/1'), ('', '/home'),
                                                ('https://example.test/', '/home'), ('//example.test/', '/home')])
def test_authenticated_bootstrap_only_allows_fixed_setup_target(next_value, expected):
    source = Path(__file__).parents[1] / 'quietclerk/server/bootstrap.js'
    script = r'''
const fs = require('fs'), vm = require('vm');
let cleaned = false, destination = null;
const context = {
  URLSearchParams,
  location: {hash: '#bootstrap=fictional&next=' + encodeURIComponent(process.argv[2]), pathname:'/', search:'', replace: x => destination = x},
  history: {replaceState: () => cleaned = true},
  document: {getElementById: () => null},
  window: {dispatchEvent: () => {}}, Event: class {},
  sessionStorage: {setItem: () => {}},
  fetch: async () => { if (!cleaned) throw Error('fragment not cleared'); return {ok:true, text:async () => '', headers:{get: () => 'fictional-csrf'}}; }
};
(async () => { await vm.runInNewContext(fs.readFileSync(process.argv[1], 'utf8'), context); console.log(JSON.stringify(destination)); })();
'''
    result = subprocess.run(['node', '-e', script, str(source), next_value], text=True, capture_output=True, check=True)
    assert json.loads(result.stdout) == expected
