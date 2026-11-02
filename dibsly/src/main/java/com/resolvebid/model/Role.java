package com.resolvebid.model;

import java.util.Collections;
import java.util.EnumSet;
import java.util.Set;

public enum Role {
    CUSTOMER(EnumSet.of(Permission.POST_REQUEST, Permission.VIEW_OWN_REQUESTS, Permission.ACCEPT_PROPOSAL, Permission.MANAGE_REQUEST)),
    PROVIDER(EnumSet.of(Permission.VIEW_OPEN_REQUESTS, Permission.SUBMIT_PROPOSAL, Permission.WITHDRAW_PROPOSAL)),
    ADMIN(EnumSet.allOf(Permission.class));

    private final Set<Permission> permissions;

    Role(Set<Permission> permissions) {
        this.permissions = Collections.unmodifiableSet(EnumSet.copyOf(permissions));
    }

    public boolean allows(Permission permission) { return permissions.contains(permission); }
    public Set<Permission> permissions() { return permissions; }
}
