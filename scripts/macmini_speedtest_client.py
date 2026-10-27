"""Raspberry client; no local speedtest fallback."""
import json
from pathlib import Path
import time
import urllib.request

CONFIG = Path('/etc/macmini-speedtest.json')


def measure(config_path=CONFIG):
    config = json.loads(Path(config_path).read_text())
    base, token = config['url'].rstrip('/'), config['token']
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    def request(path, method='GET'):
        req = urllib.request.Request(base+path, data=b'' if method=='POST' else None,
                                     headers={'Authorization':'Bearer '+token}, method=method)
        with opener.open(req, timeout=10) as response:
            return json.load(response)
    try:
        job = request('/v1/tests','POST')
        deadline = time.monotonic()+210
        while job['state']=='running':
            if time.monotonic()>deadline:
                raise RuntimeError('tempo limite da medição')
            time.sleep(2)
            job = request('/v1/tests/'+job['id'])
        if job['state']!='complete':
            raise RuntimeError(job.get('error','medição falhou'))
        result = job['result']
        if result.get('origin')!='macmini' or result.get('link_mbps',0)<1000:
            raise RuntimeError('origem de medição inválida')
        return result
    except Exception:
        # Do not expose authorization headers, config or token in logs.
        raise RuntimeError('Medição no Mac mini indisponível; verifique API e Ethernet') from None
