# Publishing SafeRevoke

Release candidate: `0.1.0a1`, under the MIT License. Creating local distributions
or pushing to GitHub does not itself upload a release to PyPI.

## First publication: one-time account setup

1. Create an account at <https://pypi.org/account/register/>.
2. Verify the email address and configure the account's required two-factor
   authentication. Keep recovery codes private.
3. Sign in and open <https://pypi.org/manage/account/publishing/>.
4. Add a pending GitHub publisher with these exact values:

| Field | Value |
|---|---|
| PyPI project name | `saferevoke` |
| GitHub repository owner | `rishisugavanam2024-beep` |
| Repository name | `disign-usability-security-` |
| Workflow filename | `publish.yml` |
| Environment name | `pypi` |

Only the workflow filename is entered, not the `.github/workflows/` prefix.
PyPI confirms the name at upload time; a pending publisher does not reserve it.

## Publish

Open the repository's **Actions → Validate and publish SafeRevoke** workflow.
Select **Run workflow**, choose branch `main`, set **publish** to true and run it.
This tests and rebuilds the selected source, validates the distributions and
uses the authorised GitHub identity to upload. No PyPI token is stored in GitHub.

A push to `main` only validates/builds; it does not publish automatically.
Manual runs with **publish** false also only validate/build.

After a successful publish job, verify the actual project and version at
<https://pypi.org/project/saferevoke/0.1.0a1/>. Then test in a fresh environment:

```powershell
python -m pip install --pre "saferevoke[pytest]==0.1.0a1"
```

Do not announce publication until the publish job succeeds and PyPI serves the
version metadata. If PyPI rejects the name, choose an available distribution
name and update metadata, the pending publisher and installation instructions.

## Future releases

Update the version in `pyproject.toml` and `saferevoke/__init__.py`, update the
changelog and validate the changes before running the publishing workflow.
An already-uploaded filename cannot be replaced; corrections need a new version.

Sources: [PyPI account management](https://docs.pypi.org/account-management/)
and [pending trusted publishers](https://docs.pypi.org/trusted-publishers/creating-a-project-through-oidc/).
