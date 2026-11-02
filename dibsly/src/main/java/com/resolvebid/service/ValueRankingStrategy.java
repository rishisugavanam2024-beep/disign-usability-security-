package com.resolvebid.service;

import com.resolvebid.model.Proposal;

public final class ValueRankingStrategy extends ProposalRankingStrategy {
    @Override
    public double score(Proposal p) {
        double priceComponent = 5000.0 / Math.max(1.0, p.price().doubleValue());
        double speedComponent = 12.0 / Math.max(1, p.etaDays());
        double warrantyComponent = Math.min(12.0, p.warrantyDays() / 30.0);
        return Math.round((priceComponent * 55 + speedComponent * 25 + warrantyComponent * 20) * 10.0) / 10.0;
    }
}
