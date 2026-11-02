"""Verify that the packaged server exits on an occupied local port."""
import json, os, socket, subprocess, sys
from pathlib import Path
root = Path(__file__).resolve().parents[1]
runtime = root / '.local' / 'startup-check'
runtime.mkdir(parents=True, exist_ok=True)
java = sys.argv[1] if len(sys.argv) > 1 else 'java'
with socket.socket() as listener:
    listener.bind(('127.0.0.1', 0))
    listener.listen(1)
    env = dict(os.environ, APP_ENV='development', DEMO_MODE='false', SECURE_COOKIES='false',
               PORT=str(listener.getsockname()[1]), DB_URL='jdbc:h2:mem:startup;DB_CLOSE_DELAY=-1;MODE=MySQL',
               DB_USER='sa', DB_PASSWORD='', ADMIN_PASSWORD='StartupCheck2026!')
    result = subprocess.run([java, '-Xmx192m', '-jar', str(root/'target/dibsly-1.0.0.jar')],
                            cwd=runtime, env=env, capture_output=True, text=True, timeout=45)
    passed = result.returncode != 0 and 'Dibsly is ready' not in result.stdout
    evidence = {'occupied_port_exits': passed, 'exit_code': result.returncode}
    (root/'verification/startup.json').write_text(json.dumps(evidence, indent=2))
    print(json.dumps(evidence))
    if not passed: raise RuntimeError('Occupied port did not fail startup correctly')
