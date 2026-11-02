package com.resolvebid.model;

import java.io.Serializable;

public record UserAccount(long id, String username, String displayName, Role role)
        implements Serializable {
    private static final long serialVersionUID = 1L;
    public boolean can(Permission permission) { return role.allows(permission); }
}
