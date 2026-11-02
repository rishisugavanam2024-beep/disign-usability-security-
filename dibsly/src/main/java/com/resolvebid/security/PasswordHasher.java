package com.resolvebid.security;

import java.security.GeneralSecurityException;
import java.security.MessageDigest;
import java.security.SecureRandom;
import javax.crypto.SecretKeyFactory;
import javax.crypto.spec.PBEKeySpec;

public final class PasswordHasher {
    public static final int ITERATIONS = 210_000;
    private static final int KEY_BITS = 256;
    private static final int SALT_BYTES = 16;
    private final SecureRandom random = new SecureRandom();

    public PasswordValue hash(char[] password) {
        byte[] salt = new byte[SALT_BYTES];
        random.nextBytes(salt);
        return new PasswordValue(derive(password, salt, ITERATIONS), salt, ITERATIONS);
    }

    public boolean verify(char[] password, byte[] expectedHash, byte[] salt, int iterations) {
        return MessageDigest.isEqual(expectedHash, derive(password, salt, iterations));
    }

    private byte[] derive(char[] password, byte[] salt, int iterations) {
        PBEKeySpec spec = new PBEKeySpec(password, salt, iterations, KEY_BITS);
        try {
            return SecretKeyFactory.getInstance("PBKDF2WithHmacSHA256").generateSecret(spec).getEncoded();
        } catch (GeneralSecurityException ex) {
            throw new IllegalStateException("Password hashing is unavailable.", ex);
        } finally {
            spec.clearPassword();
            java.util.Arrays.fill(password, '\0');
        }
    }

    public record PasswordValue(byte[] hash, byte[] salt, int iterations) { }
}
