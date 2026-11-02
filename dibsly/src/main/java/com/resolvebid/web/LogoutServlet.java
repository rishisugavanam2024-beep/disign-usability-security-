package com.resolvebid.web;

import java.io.IOException;
import jakarta.servlet.http.HttpServlet;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;

public final class LogoutServlet extends HttpServlet {
    private static final long serialVersionUID = 1L;
    @Override protected void doPost(HttpServletRequest request, HttpServletResponse response) throws IOException {
        if (!WebSupport.validCsrf(request)) { response.sendError(403); return; }
        if (request.getSession(false) != null) request.getSession(false).invalidate();
        WebSupport.redirect(request, response, "/login");
    }
}
