package com.resolvebid.model;

public record UserCredentials(UserAccount account, byte[] passwordHash, byte[] passwordSalt,
        int passwordIterations, boolean enabled) { }
