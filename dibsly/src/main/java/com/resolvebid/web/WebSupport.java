package com.resolvebid.web;

import java.io.IOException;
import com.resolvebid.model.UserAccount;
import com.resolvebid.security.Csrf;
import jakarta.servlet.ServletException;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;
import jakarta.servlet.http.HttpSession;

final class WebSupport {
    static final String USER = "resolvebid.user";
    private WebSupport() { }

    static UserAccount user(HttpServletRequest request) {
        Object value = request.getSession(false) == null ? null : request.getSession(false).getAttribute(USER);
        return value instanceof UserAccount account ? account : null;
    }

    static void page(HttpServletRequest request, HttpServletResponse response, String view)
            throws ServletException, IOException {
        request.setAttribute("csrf", Csrf.token(request.getSession(true)));
        request.getRequestDispatcher("/WEB-INF/views/" + view + ".jsp").forward(request, response);
    }

    static void flash(HttpServletRequest request, String kind, String message) {
        HttpSession session = request.getSession(true);
        session.setAttribute("flashKind", kind);
        session.setAttribute("flashMessage", message);
    }

    static void consumeFlash(HttpServletRequest request) {
        HttpSession session = request.getSession(false);
        if (session == null) return;
        request.setAttribute("flashKind", session.getAttribute("flashKind"));
        request.setAttribute("flashMessage", session.getAttribute("flashMessage"));
        session.removeAttribute("flashKind"); session.removeAttribute("flashMessage");
    }

    static boolean validCsrf(HttpServletRequest request) { return Csrf.valid(request); }
    static void redirect(HttpServletRequest request, HttpServletResponse response, String path) throws IOException {
        response.sendRedirect(request.getContextPath() + path);
    }
    static long longParam(HttpServletRequest request, String name) {
        try { return Long.parseLong(request.getParameter(name)); }
        catch (RuntimeException ex) { throw new IllegalArgumentException("Invalid " + name + "."); }
    }
}
