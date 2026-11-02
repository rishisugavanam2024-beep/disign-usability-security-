# Dibsly

**Your gig. Their pitch. Your pick.** A Java reverse freelance marketplace built from ResolveBid, with an ivory-and-coral web experience and native account permissions.

For the original **Python/PyPI SafeRevoke** demonstration, follow [PYTHON-LIBRARY-DEMO.md](PYTHON-LIBRARY-DEMO.md). Start the independent site with `./presentation.ps1 start` on port 8093, install the Python library separately during the presentation, then use native `saferevoke permissions/revoke/grant/test/report` commands. `saferevoke --help` lists every command and alias. Dibsly has no SafeRevoke runtime dependency.

## Run the demo

Requires Java 21. The release ZIP includes a built JAR: extract it and run `run-demo.cmd` directly (or `sh run-demo.sh`). To rebuild from source, use Maven 3.9+ or Docker. This development workspace also has a local Maven cache, excluded from the release.

```powershell
.\mvnw.cmd -f reactor/pom.xml verify
.\run-demo.cmd
```

Open http://localhost:8092. On Linux/macOS, use `sh run-demo.sh` after `sh mvnw -f reactor/pom.xml verify`.

| Account | Username | Demo password |
| --- | --- | --- |
| Client | `client.demo` | `DibslyDemo2026!` |
| Freelancer | `freelancer.demo` | `DibslyDemo2026!` |
| Another freelancer | `designer.demo` | `DibslyDemo2026!` |
| Administrator | `admin` | `DibslyAdmin2026!` |

The admin password above applies to a new local demo database with the default launcher settings. Existing administrator passwords are never reset on startup. Demo content is fictional, opt-in, and prohibited when `APP_ENV=production`.

## Working flows

- Public landing page, searchable/category-filtered projects, budget sorting, and pagination.
- Client/freelancer registration, login, session rotation, logout, and role-specific workspaces.
- Project briefs, private pitches, side-by-side comparisons, acceptance, withdrawal, cancellation, and completion.
- Ownership checks, live permission revocation/restoration, persistent audit events, and admin access controls.
- Accessible labels/focus, responsive navigation, password visibility controls, form feedback, local tab drafts, and reduced-motion support.
- A JSON request endpoint at `/api/requests`, scoped to the authenticated account.
- Public About, Contact, and Privacy Policy pages at `/about`, `/contact`, and `/privacy`, linked from every footer.

## Contact address

The current public support inbox is `rishisugavanam200@gmail.com`. Set the `SUPPORT_EMAIL` environment variable before starting Java to change the Contact and Privacy pages together, without editing or rebuilding them. Restart the application after changing it. Docker Compose reads the same setting from `.env`. The email button opens the visitor's email application; it does not send messages from Dibsly.

This application can be demonstrated entirely on localhost without a domain, public hosting, or an internet connection. Keep the original Eclipse project separate while exploring a future product concept. The privacy notice describes the current demonstration; review operator-specific details before any later public launch.

## Verification

`mvn -f reactor/pom.xml verify` runs Java authentication and marketplace tests, including concurrent acceptance and stale-session revocation. With the local demo running, `python tools/http-smoke.py` exercises the actual HTTP forms, CSRF, privacy, lifecycle, and revocation. It creates clearly named synthetic test accounts/projects. `tools/browser-check.cjs` captures desktop and mobile routes using Playwright and Edge; use the optional browser test setup described in [VERIFICATION.md](VERIFICATION.md).

## Deployment and scope

The project produces `target/dibsly-1.0.0.jar` and includes a multi-stage Docker build, MySQL persistence, Caddy HTTPS proxy, health checks, and environment-based secrets. Follow [DEPLOYMENT.md](DEPLOYMENT.md).

This is a deployable demonstration release, not a verified high-traffic commercial marketplace. No traffic-capacity claim is made. Sessions and login throttling are local to one application instance. Payments/escrow, messaging, file uploads, email verification, password recovery, dispute resolution, and moderation workflows are outside this release. Quotes are in INR. Public launch requires those product/operational decisions and testing on the target infrastructure.

Java packages and entry point names remain `com.resolvebid` / `ResolveBidServer` for compatibility with the original Eclipse/JavaFX source. All shipped web branding is Dibsly. The desktop client compiles against the updated service but has not received the web redesign.
