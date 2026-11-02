package com.resolvebid.web;

import java.io.IOException;
import java.util.stream.Collectors;
import com.resolvebid.model.ServiceRequest;
import com.resolvebid.model.UserAccount;
import com.resolvebid.service.MarketplaceService;
import jakarta.servlet.http.HttpServlet;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;

public final class RequestApiServlet extends HttpServlet {
    private static final long serialVersionUID = 1L;
    private final MarketplaceService service;

    public RequestApiServlet(MarketplaceService service) { this.service = service; }

    @Override protected void doGet(HttpServletRequest request, HttpServletResponse response) throws IOException {
        response.setContentType("application/json");
        response.setCharacterEncoding("UTF-8");
        UserAccount user = WebSupport.user(request);
        try {
            String json = service.requestsFor(user).stream().map(this::json).collect(Collectors.joining(",", "[", "]"));
            response.getWriter().write(json);
        } catch (com.resolvebid.exception.AuthorizationException ex) { response.setStatus(403); response.getWriter().write("{\"error\":\"Access denied\"}"); }
    }

    private String json(ServiceRequest r) {
        return "{\"id\":" + r.id() + ",\"category\":\"" + escape(r.category()) + "\",\"description\":\"" + escape(r.description()) + "\",\"status\":\"" + r.status() + "\"}";
    }

    private String escape(String value) {
        StringBuilder result = new StringBuilder();
        for (char c : value.toCharArray()) {
            if (c == '"' || c == '\\') result.append('\\').append(c);
            else if (c < 32) result.append(String.format("\\u%04x", (int)c));
            else result.append(c);
        }
        return result.toString();
    }
}
