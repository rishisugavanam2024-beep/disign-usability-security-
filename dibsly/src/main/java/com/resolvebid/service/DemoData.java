package com.resolvebid.service;

import com.resolvebid.dao.DatabaseManager;
import com.resolvebid.security.AuthService;
import com.resolvebid.model.*;
import java.math.BigDecimal;

/** Synthetic examples, available only when explicitly enabled outside production. */
public final class DemoData {
    private DemoData() { }
    public static boolean enabled() { return Boolean.parseBoolean(System.getenv().getOrDefault("DEMO_MODE", "false")); }
    public static void seed(DatabaseManager db, AuthService auth) throws Exception {
        if (!enabled()) return;
        if ("production".equalsIgnoreCase(System.getenv("APP_ENV"))) throw new IllegalStateException("DEMO_MODE must be false in production.");
        if (db.findCredentials("client.demo").isPresent()) return;
        UserAccount client = auth.register("client.demo", "Maya Chen", "DibslyDemo2026!".toCharArray(), Role.CUSTOMER);
        UserAccount studio = auth.register("studio.demo", "Oliver Studio", "DibslyDemo2026!".toCharArray(), Role.CUSTOMER);
        UserAccount freelancer = auth.register("freelancer.demo", "Alex Morgan", "DibslyDemo2026!".toCharArray(), Role.PROVIDER);
        UserAccount second = auth.register("designer.demo", "Priya Shah", "DibslyDemo2026!".toCharArray(), Role.PROVIDER);
        String[][] projects = {
            {"Design & Creative", "A fresh identity for a slow-living brand", "We are launching a small collection of everyday ceramics. Help us create a warm, distinctive wordmark, a considered color palette, and packaging guidelines. Deliverables: editable logo files, packaging mockups, and a concise brand guide.", "48000", "This month"},
            {"Development & IT", "Build a beautiful booking experience", "Our independent yoga studio needs a responsive booking website. We need a class timetable, instructor profiles, and an accessible booking form. Please include your approach to performance and handover documentation.", "85000", "This month"},
            {"Writing & Translation", "Give our coffee subscription a voice", "Write homepage copy and a five-email welcome series for a specialty coffee subscription. The voice should feel thoughtful and conversational. We will provide audience research, product details, and interview notes.", "18000", "This week"},
            {"Video & Animation", "A 30-second launch film with personality", "Create a short animated launch film for a habit-tracking app. We have a script and brand assets ready. The scope includes a storyboard, animation, captions, and exports for web and social.", "35000", "This month"},
            {"Marketing", "Help a neighborhood bakery get discovered", "Plan a four-week local content campaign for a new bakery. We need a content calendar, twelve post concepts, and a practical measurement plan. Photography will be supplied by our team.", "22000", "This week"},
            {"Development & IT", "Make our Java API easier to integrate", "Review a small Java REST API and build clear integration examples. Deliver OpenAPI documentation, request examples, and a getting-started guide. Source access will be arranged after selection.", "42000", "Flexible"},
            {"Design & Creative", "Design an accessible mobile onboarding", "Create five onboarding screens for a community gardening app. We need a simple prototype, accessible component states, and developer handoff notes. Existing brand guidelines are available.", "30000", "This week"},
            {"Business", "Turn our customer research into a clear plan", "Synthesize twelve customer interviews into an actionable findings report. Identify recurring needs, map the customer journey, and prioritize opportunities. Anonymized transcripts will be shared after hiring.", "26000", "Flexible"}
        };
        long first = 0;
        for (int i=0; i<projects.length; i++) {
            String[] p = projects[i]; UserAccount owner = i % 2 == 0 ? client : studio;
            long id = db.createRequest(owner.id(), owner.displayName(), p[0], p[1] + "\n" + p[2], p[4], new BigDecimal(p[3]));
            if (i == 0) first = id;
        }
        db.createProposal(first, freelancer.id(), freelancer.displayName(), "I will explore two visual directions, refine your chosen wordmark, and deliver print-ready packaging plus a practical brand guide. Two revision rounds are included.", new BigDecimal("42000"), 12, 14);
        db.createProposal(first, second.id(), second.displayName(), "My approach starts with a discovery workshop and a moodboard. You will receive a complete identity, editable packaging, and a recorded handover. Three revision rounds included.", new BigDecimal("46000"), 10, 30);
    }
}
