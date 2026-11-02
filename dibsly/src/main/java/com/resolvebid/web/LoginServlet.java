package com.resolvebid.web;

import java.io.IOException;
import java.util.Locale;
import java.util.Optional;
import com.resolvebid.model.UserAccount;
import com.resolvebid.security.AuthService;
import com.resolvebid.security.LoginAttemptService;
import jakarta.servlet.ServletException;
import jakarta.servlet.http.HttpServlet;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;

public final class LoginServlet extends HttpServlet {
    private static final long serialVersionUID = 1L;
    private final AuthService auth;
    private final LoginAttemptService attempts;
    public LoginServlet(AuthService auth, LoginAttemptService attempts) { this.auth = auth; this.attempts = attempts; }

    @Override protected void doGet(HttpServletRequest request, HttpServletResponse response) throws ServletException, IOException {
        if (WebSupport.user(request) != null) { WebSupport.redirect(request, response, "/app/dashboard"); return; }
        WebSupport.consumeFlash(request); WebSupport.page(request, response, "login");
    }

    @Override protected void doPost(HttpServletRequest request, HttpServletResponse response) throws ServletException, IOException {
        if (!WebSupport.validCsrf(request)) { response.sendError(403, "Security token expired. Reload and try again."); return; }
        String username = request.getParameter("username") == null ? "" : request.getParameter("username").trim();
        String key = request.getRemoteAddr() + ":" + username.toLowerCase(Locale.ROOT);
        if (attempts.blocked(key)) { request.setAttribute("error", "Too many attempts. Try again in 15 minutes."); WebSupport.page(request, response, "login"); return; }
        String password = request.getParameter("password");
        Optional<UserAccount> account = auth.authenticate(username, password == null ? new char[0] : password.toCharArray());
        if (account.isEmpty()) { attempts.failure(key); request.setAttribute("error", "Username or password is incorrect."); WebSupport.page(request, response, "login"); return; }
        attempts.success(key); request.changeSessionId(); request.getSession().setAttribute(WebSupport.USER, account.get());
        WebSupport.redirect(request, response, "/app/dashboard");
    }
}
