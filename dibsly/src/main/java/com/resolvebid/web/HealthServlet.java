package com.resolvebid.web;

import java.io.IOException;
import com.resolvebid.service.MarketplaceService;
import jakarta.servlet.http.HttpServlet;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;

public final class HealthServlet extends HttpServlet {
    private static final long serialVersionUID = 1L;
    private final MarketplaceService service;
    public HealthServlet(MarketplaceService service) { this.service = service; }
    @Override protected void doGet(HttpServletRequest request, HttpServletResponse response) throws IOException {
        try {
            service.stats(); response.setContentType("application/json"); response.getWriter().write("{\"status\":\"ok\"}");
        } catch (RuntimeException ex) {
            response.setStatus(503); response.setContentType("application/json"); response.getWriter().write("{\"status\":\"unavailable\"}");
        }
    }
}
