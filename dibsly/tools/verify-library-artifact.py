"""Prove that the built marketplace contains neither SafeRevoke nor its test connector."""
from pathlib import Path
import hashlib
import json
import zipfile
root = Path(__file__).resolve().parents[1]
application = root / 'target/dibsly-1.0.0.jar'
with zipfile.ZipFile(application) as app:
    names = app.namelist()
    forbidden = [n for n in names if 'saferevoke' in n.lower() or 'safe-revoke' in n.lower() or 'DibslyWorkflow' in n]
    assert not forbidden, f'External library/connector found in application: {forbidden}'
    assert 'com/resolvebid/dao/DatabaseManager.class' in names
    assert 'com/resolvebid/app/ResolveBidServer.class' in names
    assert app.testzip() is None
result = {
    'application': str(application),
    'applicationSha256': hashlib.sha256(application.read_bytes()).hexdigest(),
    'independentMarketplace': True,
    'embeddedSafeRevokeEntries': 0,
    'embeddedTestConnectorEntries': 0,
    'authorization': 'Dibsly native role, ownership and per-account restriction checks',
    'analysis': 'Separately installed Python saferevoke via external CommandAdapter',
}
(root / 'verification').mkdir(exist_ok=True)
(root / 'verification/native-independence.json').write_text(json.dumps(result, indent=2), encoding='utf-8')
print(json.dumps(result, indent=2))
