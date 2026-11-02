package com.resolvebid.web;

import java.io.IOException;
import java.time.LocalDate;
import java.time.format.DateTimeParseException;
import com.resolvebid.model.*;
import com.resolvebid.service.MarketplaceService;
import com.resolvebid.exception.*;
import jakarta.servlet.ServletException;
import jakarta.servlet.http.*;

public final class ActionsServlet extends HttpServlet {
    private final MarketplaceService service;
    private final SiteServlet site;
    public ActionsServlet(MarketplaceService service, SiteServlet site) { this.service = service; this.site = site; }
    @Override protected void doPost(HttpServletRequest req, HttpServletResponse res) throws IOException, ServletException {
        if (!WebSupport.validCsrf(req)) { res.sendError(403, "Your form expired. Reload the page and try again."); return; }
        UserAccount user = WebSupport.user(req);
        String action = req.getPathInfo() == null ? "" : req.getPathInfo();
        String destination = "/app/dashboard";
        try {
            switch (action) {
                case "/request" -> {
                    String title = MarketplaceService.text(req.getParameter("title"), "Project title", 8, 100);
                    String brief = MarketplaceService.text(req.getParameter("description"), "Project brief", 30, 850);
                    long id = service.postRequest(user, req.getParameter("category"), title + "\n" + brief, req.getParameter("urgency"), req.getParameter("budget"));
                    destination = "/project?id=" + id;
                    WebSupport.flash(req, "published", "Your project is live. Freelancers can now send you a pitch.");
                }
                case "/proposal" -> {
                    long id = WebSupport.longParam(req, "requestId");
                    service.submitProposal(user, service.request(id), req.getParameter("diagnosis"), req.getParameter("price"), req.getParameter("etaDays"), req.getParameter("warrantyDays"));
                    destination = "/project?id=" + id;
                    WebSupport.flash(req, "success", "Pitch sent. Only you and the client can see your offer.");
                }
                case "/accept" -> {
                    long id = WebSupport.longParam(req, "requestId"), pitchId = WebSupport.longParam(req, "proposalId");
                    Proposal pitch = service.proposalsFor(user, id).stream().filter(p -> p.id() == pitchId).findFirst().orElseThrow(() -> new IllegalArgumentException("Pitch not found."));
                    LocalDate date;
                    try { date = LocalDate.parse(req.getParameter("date") == null ? "" : req.getParameter("date")); }
                    catch (DateTimeParseException ex) { throw new IllegalArgumentException("Choose a valid project start date."); }
                    service.acceptProposal(user, service.request(id), pitch, date);
                    destination = "/project?id=" + id; WebSupport.flash(req, "success", "You're working together! Your chosen pitch is now an active contract. No payment has been collected.");
                }
                case "/cancel", "/complete" -> {
                    long id = WebSupport.longParam(req, "requestId"); service.transition(user, id, action.equals("/complete"));
                    destination = "/project?id=" + id; WebSupport.flash(req, "success", action.equals("/complete") ? "Project completed. Nicely done." : "Project closed. Pending pitches have been declined.");
                }
                case "/withdraw" -> {
                    long id = WebSupport.longParam(req, "requestId"); service.withdraw(user, id, WebSupport.longParam(req, "proposalId"));
                    destination = "/project?id=" + id; WebSupport.flash(req, "success", "Pitch withdrawn. You can submit a new offer while the project is open.");
                }
                case "/permission" -> {
                    if (!java.util.Set.of("revoke", "restore").contains(req.getParameter("change") == null ? "" : req.getParameter("change")))
                        throw new IllegalArgumentException("Choose revoke or restore.");
                    service.database().setRevoked(user, WebSupport.longParam(req, "userId"), Permission.valueOf(req.getParameter("permission")), "revoke".equals(req.getParameter("change")));
                    destination = "/app/access"; WebSupport.flash(req, "success", "Permission updated. The next protected action uses the new policy, including in existing sessions.");
                }
                default -> { res.sendError(404); return; }
            }
            res.setStatus(303); res.setHeader("Location", req.getContextPath() + destination);
        } catch (AuthorizationException ex) {
            res.setStatus(403); req.setAttribute("error", ex.getMessage()); site.render(req, res, "error");
        } catch (ValidationException | IllegalArgumentException ex) {
            res.setStatus(422); req.setAttribute("error", ex.getMessage());
            String view = action.equals("/request") ? "new" : action.equals("/permission") ? "access" : "project";
            try { site.render(req, res, view); }
            catch (RuntimeException invalid) { site.render(req, res, "error"); }
        } catch (RuntimeException ex) {
            getServletContext().log("Marketplace action failed", ex);
            res.setStatus(503); req.setAttribute("error", "We couldn't save this change. Your form is still available using Back; refresh the project before retrying."); site.render(req, res, "error");
        }
    }
}
