"""Create a local source and runnable-JAR handoff without databases, caches, or secrets."""
from pathlib import Path
import hashlib, json, zipfile, shutil
root = Path(__file__).resolve().parents[1]
output = root / 'dist'
output.mkdir(exist_ok=True)
jar = root / 'target/dibsly-1.0.0.jar'
with zipfile.ZipFile(jar) as check:
    bad = check.testzip()
    if bad: raise RuntimeError('Corrupt JAR entry: '+bad)
    manifest = check.read('META-INF/MANIFEST.MF').decode()
    assert 'com.resolvebid.app.ResolveBidServer' in manifest
    drivers = check.read('META-INF/services/java.sql.Driver').decode()
    assert 'org.h2.Driver' in drivers and 'com.mysql.cj.jdbc.Driver' in drivers
    for resource in ['site.jsp','header.jspf','footer.jspf','error.jsp','info.jsp']:
        assert 'webapp/WEB-INF/views/'+resource in check.namelist()
with zipfile.ZipFile(jar) as app:
    assert not any('saferevoke' in n.lower() or 'safe-revoke' in n.lower() or 'DibslyWorkflow' in n for n in app.namelist())
archive = output / 'dibsly-1.0.0.zip'
files = []
for name in ['src','.mvn','tools','reactor','integrations']:
    files += [p for p in (root/name).rglob('*') if p.is_file() and p.name not in ('run-detector.cmd', 'library-console.ps1', 'library-browser-check.cjs', 'library-csv-check.cjs') and '__pycache__' not in p.parts and 'target' not in p.relative_to(root).parts]
for pattern in ['*.md','*.xml','*.json','*.ps1','*.cmd','*.sh','*.ps1','Dockerfile','docker-compose.yml','Caddyfile','.env.example','.gitignore','.dockerignore','mvnw']:
    files += [p for p in root.glob(pattern) if p.is_file() and p.name != 'build-local.cmd']
for name in ['.impeccable/design.json', '.impeccable/direction.md']:
    if (root/name).is_file(): files.append(root/name)
with zipfile.ZipFile(archive,'w',zipfile.ZIP_DEFLATED) as bundle:
    for file in sorted(set(files)): bundle.write(file, 'dibsly/'+file.relative_to(root).as_posix())
    bundle.write(jar, 'dibsly/target/'+jar.name)
    for name in ('native-independence.json', 'python-connector.json', 'terminal-permissions.json', 'http-smoke.json', 'pypi-release.json'):
        file = root/'verification'/name
        if file.is_file(): bundle.write(file,'dibsly/verification/'+file.name)
hashes = {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in [jar,archive]}
(output/'SHA256SUMS.txt').write_text(''.join(f'{digest}  {name}\n' for name,digest in hashes.items()))
print(json.dumps({'archive':str(archive),'bytes':archive.stat().st_size,'sha256':hashes},indent=2))
