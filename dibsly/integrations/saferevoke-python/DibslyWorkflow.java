import com.resolvebid.config.AppConfig;
import com.resolvebid.dao.DatabaseManager;
import com.resolvebid.model.*;
import com.resolvebid.security.AuthService;
import com.resolvebid.service.*;
import com.resolvebid.util.FileService;
import com.resolvebid.web.EmbeddedWebServer;
import java.math.BigDecimal;
import java.net.*;
import java.net.http.*;
import java.nio.charset.StandardCharsets;
import java.nio.file.Path;
import java.sql.*;
import java.time.*;
import java.util.*;
import java.util.regex.*;

/** External test harness. Executes the existing packaged Dibsly web application unchanged. */
public final class DibslyWorkflow {
    static final String URL = "jdbc:h2:mem:dibsly_connector;DB_CLOSE_DELAY=-1;MODE=MySQL";
    static final String PASSWORD = "ConnectorDemo2026!";
    record GrantSpec(String id, String identity, Permission permission, String resource, String action, String description) {}
    static final List<GrantSpec> GRANTS = List.of(
        new GrantSpec("client_post", "connector.client", Permission.POST_REQUEST, "projects", "create", "Client can publish projects"),
        new GrantSpec("talent_pitch", "connector.talent", Permission.SUBMIT_PROPOSAL, "proposals", "submit", "Freelancer can submit pitches"),
        new GrantSpec("client_hire", "connector.client", Permission.ACCEPT_PROPOSAL, "contracts", "hire", "Client can hire a freelancer"),
        new GrantSpec("talent_withdraw", "connector.talent", Permission.WITHDRAW_PROPOSAL, "proposals", "withdraw", "Freelancer can withdraw a pitch"),
        new GrantSpec("client_manage", "connector.client", Permission.MANAGE_REQUEST, "projects", "manage", "Client can close or complete projects (not exercised)")
    );
    static final List<String> WORKFLOWS = List.of("publish_project", "submit_pitch", "hire_freelancer", "withdraw_pitch");
    public static void main(String[] args) throws Exception {
        if (args.length == 1 && args[0].equals("--describe")) {
            List<Object> grants = new ArrayList<>();
            for (var g : GRANTS) grants.add(Map.of("id", g.id, "principal", g.identity, "principal_type", "identity",
                "probe_identity", g.identity, "resource", g.resource, "action", g.action, "description", g.description));
            System.out.println(json(Map.of("grants", grants, "workflows", WORKFLOWS))); return;
        }
        if (!"true".equals(System.getenv("DIBSLY_CONNECTOR_TEST"))) throw new IllegalStateException("Explicit connector test opt-in required");
        if (args.length == 0 || !WORKFLOWS.contains(args[0])) throw new IllegalArgumentException("Unknown workflow");
        Set<String> denied = new HashSet<>(Arrays.asList(args).subList(1, args.length));
        if (!GRANTS.stream().map(GrantSpec::id).toList().containsAll(denied)) throw new IllegalArgumentException("Unknown grant");
        System.out.println(json(run(args[0], denied)));
    }
    static Connection open() throws SQLException { return DriverManager.getConnection(URL, "sa", ""); }
    static Map<String,Object> run(String workflow, Set<String> denied) throws Exception {
        var db = new DatabaseManager(URL, "sa", ""); db.initialize();
        var auth = new AuthService(db);
        auth.bootstrapAdmin("connector.admin", PASSWORD);
        var admin = auth.authenticate("connector.admin", PASSWORD.toCharArray()).orElseThrow();
        var client = auth.register("connector.client", "Connector Client", PASSWORD.toCharArray(), Role.CUSTOMER);
        var talent = auth.register("connector.talent", "Connector Freelancer", PASSWORD.toCharArray(), Role.PROVIDER);
        Map<String,UserAccount> accounts = Map.of(client.username(), client, talent.username(), talent);
        long project = db.createRequest(client.id(), client.displayName(), "Development & IT", "Marketplace connector fixture\nBuild a responsive website with tests and documentation.", "This week", new BigDecimal("25000"));
        // Seed fixtures through Dibsly's existing data API; the tested operation below always uses HTTP.
        if (workflow.equals("hire_freelancer") || workflow.equals("withdraw_pitch"))
            db.createProposal(project, talent.id(), talent.displayName(), "Deliver a tested website and documented handover.", new BigDecimal("20000"), 10, 14);
        long proposal = db.findProposals(project).isEmpty() ? 0 : db.findProposals(project).getFirst().id();
        List<String> snapshot = snapshot();
        Map<String,Long> before = businessState();
        int port;
        try (var reservation = new ServerSocket(0, 0, InetAddress.getByName("127.0.0.1"))) { port = reservation.getLocalPort(); }
        var config = new AppConfig("development", URL, "sa", "", port, false, "connector.admin", PASSWORD);
        var service = new MarketplaceService(db, new FileService(Path.of("data")), new ValueRankingStrategy());
        var server = new EmbeddedWebServer(service, auth, config);
        Map<String,Object> result;
        boolean started = false;
        try {
            server.start(); started = true;
            try (var browser = new Browser(port)) {
                String actor = workflow.equals("submit_pitch") || workflow.equals("withdraw_pitch") ? talent.username() : client.username();
                browser.login(actor);
                String page = workflow.equals("publish_project") ? "/app/new" : "/project?id=" + project;
                if (browser.get(page).statusCode() != 200) throw new IllegalStateException("Unable to prepare the actual form");
                String sessionBefore = browser.session();
                for (var g : GRANTS) if (denied.contains(g.id)) db.setRevoked(admin, accounts.get(g.identity).id(), g.permission, true);
                // Discard fixture/control-plane events so the trace describes only the tested request.
                try (var c = open(); var s = c.createStatement()) { s.executeUpdate("DELETE FROM authorization_events"); }
                String endpoint; Map<String,String> form;
                switch (workflow) {
                    case "publish_project" -> {
                        endpoint = "/app/action/request";
                        form = Map.of("title", "External library demonstration", "description", "Build a responsive website with accessible forms, tests, and useful documentation.", "category", "Development & IT", "urgency", "This week", "budget", "25000");
                    }
                    case "submit_pitch" -> {
                        endpoint = "/app/action/proposal";
                        form = Map.of("requestId", Long.toString(project), "diagnosis", "I will deliver tested software and a documented handover.", "price", "20000", "etaDays", "10", "warrantyDays", "14");
                    }
                    case "hire_freelancer" -> {
                        endpoint = "/app/action/accept";
                        form = Map.of("requestId", Long.toString(project), "proposalId", Long.toString(proposal), "date", LocalDate.now().toString());
                    }
                    case "withdraw_pitch" -> {
                        endpoint = "/app/action/withdraw";
                        form = Map.of("requestId", Long.toString(project), "proposalId", Long.toString(proposal));
                    }
                    default -> throw new IllegalArgumentException("Unknown workflow");
                }
                int status = browser.post(endpoint, form).statusCode();
                var after = businessState();
                Map<String,Object> effects = new LinkedHashMap<>();
                for (var key : before.keySet()) effects.put(key, after.get(key) - before.get(key));
                effects.put("same_login_session", sessionBefore.equals(browser.session()));
                List<Object> events = trace(workflow, accounts);
                List<String> errors = new ArrayList<>();
                if (events.isEmpty()) errors.add("No authorization evidence recorded by Dibsly for the operation");
                if (status != 303 && status != 403) errors.add("Unexpected application HTTP status: " + status);
                if (!sessionBefore.equals(browser.session())) errors.add("The existing login session changed");
                result = new LinkedHashMap<>();
                result.put("workflow_id", workflow); result.put("success", status == 303 && errors.isEmpty());
                result.put("output", "HTTP " + status); result.put("events", events);
                result.put("message", "POST " + endpoint + " through the packaged Dibsly server; database effects and actual authorization audit observed.");
                result.put("side_effects", effects); result.put("validation_errors", errors);
            }
        } finally {
            if (started) server.close();
            // Restore the complete test database (permissions, data, revisions, and audit), then verify it.
            try (var c = open(); var s = c.createStatement()) {
                s.execute("DROP ALL OBJECTS");
                for (String sql : snapshot) s.execute(sql);
            }
            if (!snapshot.equals(snapshot())) throw new IllegalStateException("Database snapshot restoration mismatch");
        }
        @SuppressWarnings("unchecked") var effects = (Map<String,Object>) result.get("side_effects");
        effects.put("database_restored", true);
        return result;
    }
    static List<String> snapshot() throws SQLException {
        List<String> result = new ArrayList<>();
        try (var c = open(); var s = c.createStatement(); var rs = s.executeQuery("SCRIPT")) { while (rs.next()) result.add(rs.getString(1)); }
        return result;
    }
    static Map<String,Long> businessState() throws SQLException {
        Map<String,Long> result = new LinkedHashMap<>();
        Map<String,String> queries = new LinkedHashMap<>();
        queries.put("projects", "SELECT COUNT(*) FROM service_requests");
        queries.put("pitches", "SELECT COUNT(*) FROM proposals");
        queries.put("contracts", "SELECT COUNT(*) FROM bookings");
        queries.put("withdrawn_pitches", "SELECT COUNT(*) FROM proposals WHERE status='WITHDRAWN'");
        queries.put("booked_projects", "SELECT COUNT(*) FROM service_requests WHERE status='BOOKED'");
        queries.put("accepted_pitches", "SELECT COUNT(*) FROM proposals WHERE status='ACCEPTED'");
        try (var c = open(); var s = c.createStatement()) {
            for (var entry : queries.entrySet()) try (var rs = s.executeQuery(entry.getValue())) { rs.next(); result.put(entry.getKey(), rs.getLong(1)); }
        }
        return result;
    }
    static List<Object> trace(String workflow, Map<String,UserAccount> accounts) throws SQLException {
        Map<String,String> subjects = new HashMap<>();
        accounts.forEach((name, user) -> subjects.put("dibsly:user:" + user.id(), name));
        List<Object> result = new ArrayList<>();
        try (var c = open(); var s = c.createStatement(); var rs = s.executeQuery("SELECT user_id,permission_name,allowed,reason FROM authorization_events ORDER BY id")) {
            while (rs.next()) {
                String identity = subjects.get("dibsly:user:" + rs.getLong(1)); String permission = rs.getString(2);
                var grant = GRANTS.stream().filter(g -> g.identity.equals(identity) && g.permission.name().equals(permission)).findFirst()
                    .orElseThrow(() -> new IllegalStateException("Observed permission is absent from connector inventory"));
                boolean allowed = rs.getBoolean(3);
                result.add(Map.of("workflow", workflow, "identity", identity, "resource", grant.resource, "action", grant.action,
                    "allowed", allowed, "grant_ids", allowed ? List.of(grant.id) : List.of(),
                    "checkpoint", "dibsly:" + permission, "ordinal", result.size(), "note", "Dibsly authorization audit: " + rs.getString(4)));
            }
        }
        return result;
    }
    static final class Browser implements AutoCloseable {
        final String base; final CookieManager cookies = new CookieManager(null, CookiePolicy.ACCEPT_ALL);
        final HttpClient http = HttpClient.newBuilder().cookieHandler(cookies).followRedirects(HttpClient.Redirect.NEVER).connectTimeout(Duration.ofSeconds(10)).build();
        String csrf;
        Browser(int port) { base = "http://127.0.0.1:" + port; }
        HttpResponse<String> get(String path) throws Exception { return send(HttpRequest.newBuilder(URI.create(base + path)).timeout(Duration.ofSeconds(30)).GET().build()); }
        HttpResponse<String> post(String path, Map<String,String> input) throws Exception {
            Map<String,String> fields = new LinkedHashMap<>(input); fields.put("csrf", csrf);
            List<String> parts = new ArrayList<>(); fields.forEach((key,value) -> parts.add(URLEncoder.encode(key, StandardCharsets.UTF_8) + "=" + URLEncoder.encode(value, StandardCharsets.UTF_8)));
            return send(HttpRequest.newBuilder(URI.create(base + path)).timeout(Duration.ofSeconds(30)).header("Content-Type", "application/x-www-form-urlencoded").POST(HttpRequest.BodyPublishers.ofString(String.join("&", parts))).build());
        }
        HttpResponse<String> send(HttpRequest request) throws Exception {
            var response = http.send(request, HttpResponse.BodyHandlers.ofString());
            var match = Pattern.compile("name=\"csrf\" value=\"([^\"]+)\"").matcher(response.body());
            if (match.find()) csrf = match.group(1);
            return response;
        }
        void login(String username) throws Exception {
            if (get("/login").statusCode() != 200 || post("/login", Map.of("username", username, "password", PASSWORD)).statusCode() != 302)
                throw new IllegalStateException("Real Dibsly login failed");
        }
        String session() { return cookies.getCookieStore().getCookies().stream().filter(c -> c.getName().equals("JSESSIONID")).findFirst().orElseThrow().getValue(); }
        public void close() { http.close(); }
    }
    static String json(Object value) {
        if (value == null) return "null";
        if (value instanceof Boolean || value instanceof Number) return value.toString();
        if (value instanceof Map<?,?> map) return "{" + String.join(",", map.entrySet().stream().map(e -> json(e.getKey().toString()) + ":" + json(e.getValue())).toList()) + "}";
        if (value instanceof Collection<?> values) return "[" + String.join(",", values.stream().map(DibslyWorkflow::json).toList()) + "]";
        StringBuilder out = new StringBuilder("\"");
        for (char c : value.toString().toCharArray()) {
            switch (c) { case '"' -> out.append("\\\""); case '\\' -> out.append("\\\\"); case '\n' -> out.append("\\n"); case '\r' -> out.append("\\r"); case '\t' -> out.append("\\t"); default -> { if (c < 32) out.append(String.format("\\u%04x", (int)c)); else out.append(c); } }
        }
        return out.append('"').toString();
    }
}
