package com.resolvebid.model;

public final class ServiceProvider extends MarketplaceUser {
    private final String specialty;

    public ServiceProvider(long id, String name, String email, String specialty) {
        super(id, name, email);
        this.specialty = specialty;
    }

    public String specialty() { return specialty; }
    @Override public String roleLabel() { return "Provider · " + specialty; }
}
