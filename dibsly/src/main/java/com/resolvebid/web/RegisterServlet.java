package com.resolvebid.web;

import java.io.IOException;
import com.resolvebid.exception.ValidationException;
import com.resolvebid.model.Role;
import com.resolvebid.model.UserAccount;
import com.resolvebid.security.AuthService;
import jakarta.servlet.ServletException;
import jakarta.servlet.http.HttpServlet;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;

public final class RegisterServlet extends HttpServlet {
    private static final long serialVersionUID = 1L;
    private final AuthService auth;
    public RegisterServlet(AuthService auth) { this.auth = auth; }
    @Override protected void doGet(HttpServletRequest request, HttpServletResponse response) throws ServletException, IOException {
        WebSupport.page(request, response, "register");
    }
    @Override protected void doPost(HttpServletRequest request, HttpServletResponse response) throws ServletException, IOException {
        if (!WebSupport.validCsrf(request)) { response.sendError(403); return; }
        try {
            Role role = Role.valueOf(request.getParameter("role") == null ? "" : request.getParameter("role"));
            String password = request.getParameter("password");
            UserAccount account = auth.register(request.getParameter("username"), request.getParameter("displayName"),
                    password == null ? new char[0] : password.toCharArray(), role);
            request.changeSessionId(); request.getSession().setAttribute(WebSupport.USER, account);
            WebSupport.redirect(request, response, "/app/dashboard");
        } catch (ValidationException | IllegalArgumentException ex) {
            response.setStatus(422);
            request.setAttribute("error", ex.getMessage() == null ? "Choose a valid role." : ex.getMessage());
            WebSupport.page(request, response, "register");
        } catch (com.resolvebid.exception.DataAccessException ex) {
            response.setStatus(409); request.setAttribute("error", "We couldn't create that account. Try a different username or try again shortly.");
            WebSupport.page(request, response, "register");
        }
    }
}
