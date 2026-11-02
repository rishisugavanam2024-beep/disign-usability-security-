package com.resolvebid.model;

public final class Customer extends MarketplaceUser {
    public Customer(long id, String name, String email) { super(id, name, email); }
    @Override public String roleLabel() { return "Customer"; }
}
