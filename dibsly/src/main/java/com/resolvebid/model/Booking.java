package com.resolvebid.model;

import java.time.LocalDate;

public record Booking(long id, long requestId, long proposalId, String providerName,
        String category, LocalDate scheduledFor, String status) { }
