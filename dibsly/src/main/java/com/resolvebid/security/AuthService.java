package com.resolvebid.security;

import java.util.Arrays;
import java.util.Locale;
import java.util.Optional;
import java.util.regex.Pattern;
import com.resolvebid.dao.DatabaseManager;
import com.resolvebid.exception.ValidationException;
import com.resolvebid.model.Role;
import com.resolvebid.model.UserAccount;
import com.resolvebid.model.UserCredentials;
import com.resolvebid.security.PasswordHasher.PasswordValue;

public final class AuthService {
    private static final Pattern USERNAME = Pattern.compile("[A-Za-z0-9._-]{3,32}");
    private final DatabaseManager database;
    private final PasswordHasher hasher;

    public AuthService(DatabaseManager database) { this(database, new PasswordHasher()); }
    AuthService(DatabaseManager database, PasswordHasher hasher) { this.database = database; this.hasher = hasher; }

    public void bootstrapAdmin(String username, String password) {
        if (database.findCredentials(username).isPresent()) return;
        char[] chars = password.toCharArray();
        PasswordValue value = hasher.hash(chars);
        database.createUser(username.toLowerCase(Locale.ROOT), "Dibsly Administrator",
                value.hash(), value.salt(), value.iterations(), Role.ADMIN);
    }

    public Optional<UserAccount> authenticate(String username, char[] password) {
        try {
            if (username == null || password == null || username.length() > 64 || password.length > 128) return Optional.empty();
            Optional<UserCredentials> match = database.findCredentials(username.trim());
            if (match.isEmpty() || !match.get().enabled()) return Optional.empty();
            UserCredentials credentials = match.get();
            return hasher.verify(password, credentials.passwordHash(), credentials.passwordSalt(),
                    credentials.passwordIterations()) ? Optional.of(credentials.account()) : Optional.empty();
        } finally {
            if (password != null) Arrays.fill(password, '\0');
        }
    }

    public UserAccount register(String username, String displayName, char[] password, Role role)
            throws ValidationException {
        String normalized = username == null ? "" : username.trim().toLowerCase(Locale.ROOT);
        String name = displayName == null ? "" : displayName.trim();
        if (!USERNAME.matcher(normalized).matches())
            throw new ValidationException("Username must be 3–32 letters, numbers, dots, hyphens, or underscores.");
        if (name.length() < 2 || name.length() > 100)
            throw new ValidationException("Display name must be between 2 and 100 characters.");
        if (role != Role.CUSTOMER && role != Role.PROVIDER)
            throw new ValidationException("Choose either customer or provider.");
        validatePassword(password);
        if (database.findCredentials(normalized).isPresent()) throw new ValidationException("That username is already in use.");
        PasswordValue value = hasher.hash(password);
        long id = database.createUser(normalized, name, value.hash(), value.salt(), value.iterations(), role);
        return new UserAccount(id, normalized, name, role);
    }

    private void validatePassword(char[] password) throws ValidationException {
        String value = password == null ? "" : new String(password);
        boolean valid = value.length() >= 12 && value.length() <= 128 && value.chars().anyMatch(Character::isUpperCase)
                && value.chars().anyMatch(Character::isLowerCase)
                && value.chars().anyMatch(Character::isDigit)
                && value.chars().anyMatch(c -> !Character.isLetterOrDigit(c));
        if (!valid) throw new ValidationException("Use at least 12 characters with upper, lower, number, and symbol.");
    }
}
