import ast


def replace_function(source,name,replacement):
    node=next(n for n in ast.parse(source).body if isinstance(n,ast.FunctionDef) and n.name==name)
    lines=source.splitlines(keepends=True);lines[node.lineno-1:node.end_lineno]=[replacement+'\n']
    result=''.join(lines);ast.parse(result);return result


def patched(source):
    if 'from nas_recovery import record_critical, recover' not in source:
        source=source.replace('import json\n','import json\nfrom nas_recovery import record_critical, recover\n',1)
    source=replace_function(source,'clear_fsd','''def clear_fsd() -> bool:
    def status():
        result = subprocess.run(["upsc", UPS_NAME, "ups.status"],capture_output=True,text=True,timeout=5)
        return result.stdout.split() if result.returncode == 0 else []
    current = status()
    if "OL" in current and "FSD" not in current:
        return True
    try:
        for service in ["nut-monitor","nut-server","nut-driver@ragtech"]:
            subprocess.run(["systemctl","stop",service],check=True,capture_output=True,timeout=20)
        for service in ["nut-driver@ragtech","nut-server","nut-monitor"]:
            subprocess.run(["systemctl","start",service],check=True,capture_output=True,timeout=20)
            time.sleep(2)
        for _ in range(10):
            current = status()
            if "OL" in current and "FSD" not in current:
                return True
            time.sleep(1)
    except Exception:
        log.exception("Falha ao recuperar pilha NUT")
    return False''')
    source=replace_function(source,'power_restored_sequence','''def power_restored_sequence() -> None:
    with _recovery_lock:
        from pathlib import Path
        def sample():
            try:
                return json.loads(Path("/run/ragtech-power/sample.json").read_text())
            except (OSError,ValueError):
                return None
        def gateway():
            return subprocess.run(["ping","-c","1","-W","1","192.168.50.1"],capture_output=True).returncode == 0
        def fsd():
            result = subprocess.run(["upsc",UPS_NAME,"ups.status"],capture_output=True,text=True,timeout=5)
            return result.returncode == 0 and "FSD" in result.stdout.split()
        recover(sample,ping_nas,gateway,clear_fsd,send_wol,
                lambda text: send_telegram(text,parse_mode=None),fsd)''')
    anchor='            publish_sample(data)'
    if '            record_critical(data)' not in source:
        if source.count(anchor)!=1:raise ValueError('Heartbeat anchor missing')
        source=source.replace(anchor,anchor+'\n            record_critical(data)',1)
    anchor='    recovery_thread = None'
    if anchor in source:
        source=source.replace(anchor,'    recovery_thread = threading.Thread(target=power_restored_sequence, daemon=True)\n    recovery_thread.start()',1)
    ast.parse(source)
    return source
