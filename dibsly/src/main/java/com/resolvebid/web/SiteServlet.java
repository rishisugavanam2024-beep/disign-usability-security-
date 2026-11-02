package com.resolvebid.web;

import java.io.IOException;
import java.util.*;
import com.resolvebid.model.*;
import com.resolvebid.service.*;
import com.resolvebid.exception.AuthorizationException;
import jakarta.servlet.ServletException;
import jakarta.servlet.http.*;

public final class SiteServlet extends HttpServlet {
    private final MarketplaceService service;
    private final String supportEmail = supportEmail();
    public SiteServlet(MarketplaceService service) { this.service = service; }
    @Override protected void doGet(HttpServletRequest req, HttpServletResponse res) throws ServletException, IOException {
        String path = req.getServletPath();
        String view = switch(path) {
            case "/explore" -> "explore"; case "/project" -> "project";
            case "/app/dashboard" -> "workspace"; case "/app/new" -> "new";
            case "/app/access" -> "access"; case "/how-it-works" -> "guide";
            case "/about" -> "about"; case "/contact" -> "contact"; case "/privacy" -> "privacy"; default -> "home";
        };
        try { render(req, res, view); }
        catch (AuthorizationException ex) { res.setStatus(403); req.setAttribute("error", ex.getMessage()); render(req, res, "error"); }
        catch (IllegalArgumentException ex) { res.setStatus(404); req.setAttribute("error", "That project could not be found."); render(req, res, "error"); }
    }
    public void render(HttpServletRequest req, HttpServletResponse res, String view) throws ServletException, IOException {
        UserAccount user = WebSupport.user(req);
        req.setAttribute("user", user); req.setAttribute("view", view); req.setAttribute("demo", DemoData.enabled());
        if (Set.of("about", "contact", "privacy").contains(view)) {
            req.setAttribute("supportEmail", supportEmail);
            req.setAttribute("pageTitle", (view.equals("privacy") ? "Privacy Policy" : view.equals("about") ? "About" : "Contact") + " Â· Dibsly");
            WebSupport.page(req, res, "info");
            return;
        }
        req.setAttribute("categories", MarketplaceService.CATEGORIES); req.setAttribute("timelines", MarketplaceService.TIMELINES);
        if (view.equals("home") || view.equals("explore")) {
            String q = bounded(req.getParameter("q"), 120), category = bounded(req.getParameter("category"), 60), sort = bounded(req.getParameter("sort"), 20);
            int page = 1; try { page = Math.max(1, Math.min(10000, Integer.parseInt(req.getParameter("page")))); } catch (RuntimeException ignored) { }
            List<ServiceRequest> items = service.browse(q, category, sort, page);
            req.setAttribute("hasNext", items.size() > 12); req.setAttribute("pageNumber", page);
            req.setAttribute("projects", items.subList(0, Math.min(items.size(), view.equals("home") ? 4 : 12)));
            req.setAttribute("q", q); req.setAttribute("category", category); req.setAttribute("sort", sort);
        }
        if (view.equals("workspace")) {
            req.setAttribute("projects", service.requestsFor(user)); req.setAttribute("stats", service.stats(user));
        }
        if (view.equals("new")) service.require(user, Permission.POST_REQUEST);
        if (view.equals("project")) {
            String idValue = req.getParameter("id") != null ? req.getParameter("id") : req.getParameter("requestId");
            ServiceRequest project = service.requestFor(user, Long.parseLong(idValue));
            req.setAttribute("project", project); req.setAttribute("owner", service.owns(user, project.id()));
            req.setAttribute("pitches", user == null ? List.of() : service.proposalsFor(user, project.id()));
            req.setAttribute("canPitch", service.can(user, Permission.SUBMIT_PROPOSAL));
        }
        if (view.equals("access")) {
            req.setAttribute("accounts", service.database().users(user));
            req.setAttribute("events", service.database().auditEvents(user));
            Map<Long, Set<Permission>> revocations = new LinkedHashMap<>();
            for (UserAccount account : service.database().users(user)) revocations.put(account.id(), service.database().revoked(account.id()));
            req.setAttribute("revocations", revocations);
        }
        WebSupport.consumeFlash(req); WebSupport.page(req, res, "site");
    }
    private static String bounded(String value, int max) { return value == null ? "" : value.substring(0, Math.min(max, value.length())).trim(); }
    private static String supportEmail() {
        String value = System.getenv().getOrDefault("SUPPORT_EMAIL", "rishisugavanam200@gmail.com").trim();
        if (value.length() > 254 || !value.matches("[A-Za-z0-9._+%-]+@[A-Za-z0-9.-]+\\.[A-Za-z]{2,63}"))
            throw new IllegalStateException("SUPPORT_EMAIL must be a valid public contact email address.");
        return value;
    }
}
