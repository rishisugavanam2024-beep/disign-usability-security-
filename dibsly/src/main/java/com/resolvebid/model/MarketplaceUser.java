package com.resolvebid.model;

public abstract class MarketplaceUser {
    private final long id;
    private final String name;
    private final String email;

    protected MarketplaceUser(long id, String name, String email) {
        this.id = id;
        this.name = name;
        this.email = email;
    }

    public long id() { return id; }
    public String name() { return name; }
    public String email() { return email; }
    public abstract String roleLabel();

    @Override
    public String toString() { return name + " · " + roleLabel(); }
}
