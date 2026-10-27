"""Patch the current deployed daemon without copying its credentials."""
from pathlib import Path
import ast
import sys


def patched(source):
    if 'from raspberry_lifecycle import' in source:
        return source
    source = source.replace('import json\n', 'import json\nfrom raspberry_lifecycle import NasMonitor, boot_notification_loop\n', 1)
    start = source.index('def send_telegram(')
    end = source.index('\ndef ping_nas()', start)
    source = source[:start] + '''def send_telegram(text: str, parse_mode="Markdown") -> bool:
    params = {"chat_id": CHAT_ID, "text": text}
    if parse_mode:
        params["parse_mode"] = parse_mode
    payload = urllib.parse.urlencode(params).encode()
    try:
        with urllib.request.urlopen(
            urllib.request.Request(
                f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage", data=payload,
            ), timeout=10,
        ) as response:
            return bool(json.loads(response.read()).get("ok"))
    except Exception:
        # Do not log URLs or exceptions containing the Telegram token.
        log.warning("Telegram falhou; mensagem nao confirmada")
        return False

''' + source[end:]
    anchor = '    cmd_thread = threading.Thread(target=telegram_command_loop, daemon=True)'
    if anchor not in source:
        raise ValueError('Main thread anchor missing')
    source = source.replace(anchor, '''    threading.Thread(
        target=boot_notification_loop,
        args=(lambda text: send_telegram(text, parse_mode=None),), daemon=True,
    ).start()

''' + anchor, 1)
    if '    last_nas_online = None' not in source:
        raise ValueError('NAS state anchor missing')
    source = source.replace('    last_nas_online = None', '    nas_monitor = NasMonitor()', 1)
    start = source.index('            nas_online = ping_nas()')
    end = source.index('\n        time.sleep(POLL_SEC)', start)
    source = source[:start] + '''            message = nas_monitor.observe(ping_nas())
            if message:
                log.info("Mudanca confirmada na acessibilidade do NAS")
                send_telegram(message)
''' + source[end:]
    ast.parse(source)
    return source


if __name__ == '__main__':
    target = Path(sys.argv[1])
    source = patched(target.read_text())
    temp = target.with_suffix('.new')
    temp.write_text(source)
    temp.chmod(target.stat().st_mode & 0o777)
    temp.replace(target)
