# Product

<!-- impeccable:product-schema 1 -->

## Platform
Web; retained JavaFX desktop client.

## Stack
Java 21, Servlets/JSP on embedded Tomcat, JDBC, H2 locally, MySQL deployment configuration, Maven, Docker, Caddy, plain CSS/JavaScript.

## Users
Clients publish briefs and choose freelancers. Freelancers propose approach, quote, delivery, and support. Administrators manage permissions and audit events.

## Product Purpose
Dibsly is a reverse freelance marketplace with private, comparable pitches and a live permission-revocation demonstration.

## Positioning
Your gig. Their pitch. Your pick. Compare approaches alongside price.

## Operating Context
Laptop and phone use in ordinary daylight. Public pages introduce the workflow; workspaces support decisions. JavaFX compiles but has not received the web redesign or UI verification.

## Capabilities and Constraints
Search, filters, sorting, registration, login, pitching, acceptance, withdrawal, cancellation, and completion are implemented. Pitches are visible to their author, project owner, and administrators; competing freelancers cannot see them. Ownership is enforced server-side.

Quotes use INR. Acceptance records an agreement without collecting payment. Payments/escrow, messaging, uploads, email verification, recovery, disputes, and moderation are outside this release.

Dibsly owns its native permission checks, account restrictions, protected transactions and audit trail. The original Python SafeRevoke package tests it through an external connector; no SafeRevoke runtime dependency is shipped. Revocation governs future access, not committed agreements or previously viewed data. Sessions and throttling are instance-local. Demo data is synthetic, opt-in, and prohibited in production. Secrets use environment configuration.

Legacy com.resolvebid packages and ResolveBidServer remain for compatibility. Retain the academic Java concepts, shared service layer, and responsive JavaFX background work.

## Brand Commitments
Bright editorial job board: ivory, coral, readable briefs, and comparable pitches. Direct, welcoming, practical voice. Explicit illustrative content.

## Evidence on Hand
README.md, LIBRARY-DEMO.md, and VERIFICATION.md record scope. Dibsly has marketplace and HTTP integration checks; see VERIFICATION.md for current counts and evidence. Compose configuration validated; live Docker/MySQL/TLS was untested. No high-traffic, bug-free, penetration-test, or distributed-deployment claim.

## Product Principles
Clear deliverables; comparable terms; private pitches; server-side ownership; actionable denials; honest demo disclosures.

## Accessibility & Inclusion
Keyboard access, visible focus, labeled fields, readable contrast, responsive layouts, reduced motion, explicit currency/status, and clear recovery.
