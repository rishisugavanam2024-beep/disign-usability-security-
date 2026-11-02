package com.resolvebid.security;

import java.security.MessageDigest;
import java.security.SecureRandom;
import java.util.Base64;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpSession;

public final class Csrf {
    public static final String SESSION_KEY = "csrfToken";
    private static final SecureRandom RANDOM = new SecureRandom();
    private Csrf() { }

    public static String token(HttpSession session) {
        Object existing = session.getAttribute(SESSION_KEY);
        if (existing instanceof String token) return token;
        byte[] bytes = new byte[32];
        RANDOM.nextBytes(bytes);
        String token = Base64.getUrlEncoder().withoutPadding().encodeToString(bytes);
        session.setAttribute(SESSION_KEY, token);
        return token;
    }

    public static boolean valid(HttpServletRequest request) {
        Object expected = request.getSession(false) == null ? null
                : request.getSession(false).getAttribute(SESSION_KEY);
        String actual = request.getParameter("csrf");
        return expected instanceof String token && actual != null
                && MessageDigest.isEqual(token.getBytes(java.nio.charset.StandardCharsets.UTF_8),
                        actual.getBytes(java.nio.charset.StandardCharsets.UTF_8));
    }
}
