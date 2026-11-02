package com.resolvebid.model;

import java.math.BigDecimal;
import java.time.LocalDateTime;

public record Proposal(long id, long requestId, String providerName, String diagnosis,
        BigDecimal price, int etaDays, int warrantyDays, ProposalStatus status,
        LocalDateTime createdAt) { }
