package com.resolvebid.service;

import com.resolvebid.model.Proposal;

public abstract class ProposalRankingStrategy {
    public abstract double score(Proposal proposal);
    public String explanation() { return "Higher scores balance price, response time and warranty."; }
}
