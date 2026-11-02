package com.resolvebid.service;

import java.nio.file.Path;
import java.time.LocalDate;
import java.util.*;
import com.resolvebid.dao.DatabaseManager;
import com.resolvebid.exception.AuthorizationException;
import com.resolvebid.exception.ValidationException;
import com.resolvebid.model.*;
import com.resolvebid.util.FileService;
import com.resolvebid.util.Validation;

public final class MarketplaceService {
    public static final String[] CATEGORIES = {"Design & Creative", "Development & IT", "Writing & Translation", "Marketing", "Video & Animation", "Business", "Other"};
    public static final String[] TIMELINES = {"Within 24 hours", "This week", "This month", "Flexible"};
    private final DatabaseManager database;
    private final FileService files;
    private final ProposalRankingStrategy ranking;
    public MarketplaceService(DatabaseManager database, FileService files, ProposalRankingStrategy ranking) {
        this.database = database; this.files = files; this.ranking = ranking;
    }
    public DatabaseManager database() { return database; }
    public UserAccount refresh(UserAccount user) {
        if (user == null) throw new AuthorizationException("Sign in to continue.");
        return database.currentUser(user.id()).orElseThrow(() -> new AuthorizationException("Your account is unavailable. Sign in again."));
    }
    public boolean can(UserAccount user, Permission permission) { return database.allowed(user, permission); }
    public void require(UserAccount user, Permission permission) {
        if (!can(user, permission)) throw new AuthorizationException("You do not currently have permission for this action.");
    }
    public long postRequest(UserAccount user, String category, String description, String urgency, String budget) throws ValidationException {
        if (category == null || !List.of(CATEGORIES).contains(category)) throw new ValidationException("Choose a project category.");
        if (urgency == null || !List.of(TIMELINES).contains(urgency)) throw new ValidationException("Choose when you would like to start.");
        return database.post(user, category, text(description, "Project brief", 12, 1000), urgency, Validation.positiveMoney(budget, "Budget"));
    }
    public void submitProposal(UserAccount user, ServiceRequest request, String scope, String price, String days, String support) throws ValidationException {
        if (request == null) throw new ValidationException("Choose an available project.");
        database.propose(user, request.id(), text(scope, "Your pitch", 12, 1000), Validation.positiveMoney(price, "Quote"),
                Validation.positiveInt(days, "Delivery"), Validation.positiveInt(support, "Support"));
    }
    public void acceptProposal(UserAccount user, ServiceRequest request, Proposal proposal, LocalDate date) throws ValidationException {
        if (request == null || proposal == null || proposal.requestId() != request.id()) throw new ValidationException("Choose a pitch for this project.");
        if (date == null || date.isBefore(LocalDate.now()) || date.isAfter(LocalDate.now().plusYears(1))) throw new ValidationException("Choose a start date within the next year.");
        database.accept(user, request.id(), proposal.id(), date);
    }
    public void transition(UserAccount user, long id, boolean complete) { database.transition(user, id, complete); }
    public void withdraw(UserAccount user, long requestId, long proposalId) { database.withdraw(user, requestId, proposalId); }
    public ServiceRequest request(long id) { return database.findRequest(id).orElseThrow(() -> new IllegalArgumentException("Project not found.")); }
    public ServiceRequest requestFor(UserAccount user, long id) {
        ServiceRequest item = request(id);
        if (item.status() == RequestStatus.OPEN) return item;
        UserAccount actual = refresh(user);
        if (actual.role() != Role.ADMIN && !database.requestOwnedBy(id, actual.id()) && database.visibleProposals(actual, id).isEmpty())
            throw new AuthorizationException("This project is private to its participants.");
        return item;
    }
    public boolean owns(UserAccount user, long id) { return user != null && (user.role() == Role.ADMIN || database.requestOwnedBy(id, user.id())); }
    public List<ServiceRequest> browse(String query, String category, String sort, int page) { return database.browse(query, category, sort, page); }
    public List<ServiceRequest> requestsFor(UserAccount user) {
        return database.workspace(user);
    }
    public List<Proposal> proposalsFor(UserAccount user, long requestId) {
        return database.visibleProposals(user, requestId);
    }
    public List<Proposal> rankedProposals(UserAccount user, long requestId) { return proposalsFor(user, requestId); }
    public List<Booking> bookings(UserAccount user) {
        Set<Long> visible = new HashSet<>(); requestsFor(user).forEach(r -> visible.add(r.id()));
        return database.findBookings().stream().filter(b -> visible.contains(b.requestId())).toList();
    }
    public DashboardStats stats() { return database.stats(); }
    public DashboardStats stats(UserAccount user) {
        var projects = requestsFor(user);
        long pitches = projects.stream().mapToLong(p -> proposalsFor(user, p.id()).size()).sum();
        return new DashboardStats(projects.stream().filter(p -> p.status() == RequestStatus.OPEN).count(), pitches,
                projects.stream().filter(p -> p.status() == RequestStatus.BOOKED).count(), projects.stream().filter(p -> p.status() == RequestStatus.COMPLETED).count());
    }
    public Map<Long, Double> scores(List<Proposal> proposals) {
        Map<Long, Double> scores = new LinkedHashMap<>(); proposals.forEach(p -> scores.put(p.id(), ranking.score(p))); return scores;
    }
    public String rankingExplanation() { return "Compare price, delivery time, and included support. Choose the fit for your brief."; }
    public Set<String> supportedCategories() { return new LinkedHashSet<>(List.of(CATEGORIES)); }
    public Path exportBookings(UserAccount user) throws Exception { require(user, Permission.ADMINISTER); return files.exportBookings(bookings(user)); }
    public static String text(String value, String label, int min, int max) throws ValidationException {
        String result = Validation.required(value, label);
        if (result.length() < min || result.length() > max) throw new ValidationException(label + " must contain " + min + "–" + max + " characters.");
        return result;
    }
}
