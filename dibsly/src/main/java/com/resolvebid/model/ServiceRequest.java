package com.resolvebid.model;

import java.math.BigDecimal;
import java.time.LocalDateTime;

public record ServiceRequest(long id, String customerName, String category, String description,
        String urgency, BigDecimal budget, RequestStatus status, LocalDateTime createdAt) {
    public String title() { return description.split("\\n", 2)[0]; }
    public String brief() { String[] parts = description.split("\\n", 2); return parts.length > 1 ? parts[1] : description; }
    @Override public String toString() {
        return "#" + id + " · " + category + " · " + description;
    }
}
