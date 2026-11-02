package com.resolvebid.model;

import java.time.LocalDateTime;

public record AuditEvent(long id, String actor, String action, String detail, LocalDateTime time) { }
