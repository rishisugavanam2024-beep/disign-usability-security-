package com.resolvebid.security;

import java.time.Duration;
import java.time.Instant;
import java.util.concurrent.ConcurrentHashMap;

public final class LoginAttemptService {
    private static final int MAX_ATTEMPTS = 5;
    private static final Duration WINDOW = Duration.ofMinutes(15);
    private final ConcurrentHashMap<String, Attempt> attempts = new ConcurrentHashMap<>();

    public boolean blocked(String key) {
        Attempt attempt = attempts.get(key);
        if (attempt == null) return false;
        if (attempt.started.plus(WINDOW).isBefore(Instant.now())) {
            attempts.remove(key);
            return false;
        }
        return attempt.count >= MAX_ATTEMPTS;
    }

    public void failure(String key) {
        attempts.compute(key, (ignored, current) -> {
            if (current == null || current.started.plus(WINDOW).isBefore(Instant.now())) {
                return new Attempt(1, Instant.now());
            }
            return new Attempt(current.count + 1, current.started);
        });
    }

    public void success(String key) { attempts.remove(key); }
    private record Attempt(int count, Instant started) { }
}
