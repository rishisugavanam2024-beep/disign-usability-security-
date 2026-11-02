package com.resolvebid.dao;

import java.math.BigDecimal;
import java.nio.file.Path;
import java.sql.Connection;
import java.sql.DriverManager;
import java.sql.PreparedStatement;
import java.sql.ResultSet;
import java.sql.SQLException;
import java.sql.Statement;
import java.time.LocalDate;
import java.time.LocalDateTime;
import java.util.ArrayList;
import java.util.List;
import java.util.Optional;
import java.util.Set;
import java.util.EnumSet;
import com.resolvebid.model.Permission;
import com.resolvebid.model.AuditEvent;
import com.resolvebid.exception.AuthorizationException;
import com.resolvebid.exception.DataAccessException;
import com.resolvebid.model.Booking;
import com.resolvebid.model.DashboardStats;
import com.resolvebid.model.Proposal;
import com.resolvebid.model.ProposalStatus;
import com.resolvebid.model.RequestStatus;
import com.resolvebid.model.Role;
import com.resolvebid.model.ServiceRequest;
import com.resolvebid.model.UserAccount;
import com.resolvebid.model.UserCredentials;

public final class DatabaseManager {
    private final String url;
    private final String user;
    private final String password;
    public DatabaseManager(Path databasePath) {
        this("jdbc:h2:file:" + databasePath.toAbsolutePath().toString().replace('\\', '/')
                + ";AUTO_SERVER=TRUE;MODE=MySQL", "sa", "");
    }

    public DatabaseManager(String url, String user, String password) {
        this.url = url;
        this.user = user;
        this.password = password;
    }

    private Connection connection() throws SQLException { return DriverManager.getConnection(url, user, password); }

    public void initialize() {
        String[] schema = {
            "CREATE TABLE IF NOT EXISTS users (id BIGINT AUTO_INCREMENT PRIMARY KEY, username VARCHAR(64) UNIQUE NOT NULL, display_name VARCHAR(100) NOT NULL, password_hash VARBINARY(64) NOT NULL, password_salt VARBINARY(32) NOT NULL, password_iterations INT NOT NULL, role VARCHAR(20) NOT NULL, enabled BOOLEAN NOT NULL, created_at TIMESTAMP NOT NULL)",
            "CREATE TABLE IF NOT EXISTS service_requests (id BIGINT AUTO_INCREMENT PRIMARY KEY, customer_user_id BIGINT NULL, customer_name VARCHAR(100) NOT NULL, category VARCHAR(60) NOT NULL, description VARCHAR(1000) NOT NULL, urgency VARCHAR(30) NOT NULL, budget DECIMAL(12,2) NOT NULL, status VARCHAR(20) NOT NULL, created_at TIMESTAMP NOT NULL, FOREIGN KEY(customer_user_id) REFERENCES users(id))",
            "CREATE TABLE IF NOT EXISTS proposals (id BIGINT AUTO_INCREMENT PRIMARY KEY, request_id BIGINT NOT NULL, provider_user_id BIGINT NULL, provider_name VARCHAR(100) NOT NULL, diagnosis VARCHAR(1000) NOT NULL, price DECIMAL(12,2) NOT NULL, eta_days INT NOT NULL, warranty_days INT NOT NULL, status VARCHAR(20) NOT NULL, created_at TIMESTAMP NOT NULL, FOREIGN KEY(request_id) REFERENCES service_requests(id), FOREIGN KEY(provider_user_id) REFERENCES users(id))",
            "CREATE TABLE IF NOT EXISTS bookings (id BIGINT AUTO_INCREMENT PRIMARY KEY, request_id BIGINT NOT NULL, proposal_id BIGINT NOT NULL, scheduled_for DATE NOT NULL, status VARCHAR(30) NOT NULL, FOREIGN KEY(request_id) REFERENCES service_requests(id), FOREIGN KEY(proposal_id) REFERENCES proposals(id))",
            "CREATE TABLE IF NOT EXISTS reviews (id BIGINT AUTO_INCREMENT PRIMARY KEY, booking_id BIGINT NOT NULL, rating INT NOT NULL, comment VARCHAR(1000), FOREIGN KEY(booking_id) REFERENCES bookings(id))",
            "CREATE TABLE IF NOT EXISTS app_migrations (name VARCHAR(80) PRIMARY KEY)",
            "CREATE TABLE IF NOT EXISTS authorization_events (id BIGINT AUTO_INCREMENT PRIMARY KEY, user_id BIGINT NOT NULL, permission_name VARCHAR(40) NOT NULL, allowed BOOLEAN NOT NULL, reason VARCHAR(40) NOT NULL, occurred_ms BIGINT NOT NULL)",
            "CREATE TABLE IF NOT EXISTS permission_revocations (user_id BIGINT NOT NULL, permission VARCHAR(40) NOT NULL, PRIMARY KEY(user_id,permission), FOREIGN KEY(user_id) REFERENCES users(id))",
            "CREATE TABLE IF NOT EXISTS audit_events (id BIGINT AUTO_INCREMENT PRIMARY KEY, actor VARCHAR(64) NOT NULL, action VARCHAR(40) NOT NULL, detail VARCHAR(500) NOT NULL, created_at TIMESTAMP NOT NULL)"
        };
        try (Connection c = connection(); Statement s = c.createStatement()) {
            for (String sql : schema) s.execute(sql);
        } catch (SQLException ex) { throw new DataAccessException("Could not initialize the database.", ex); }
        migrateLegacyAccess();
    }

    /** Preserve prior restrictions once when upgrading an existing local database. */
    private void migrateLegacyAccess() {
        transaction(c -> {
            try (var ps=c.prepareStatement("SELECT name FROM app_migrations WHERE name='native-authorization-v1'"); var rs=ps.executeQuery()) {
                if (rs.next()) return null;
            }
            boolean oldTable=false;
            try (var tables=c.getMetaData().getTables(c.getCatalog(), null, "%", new String[]{"TABLE"})) {
                while(tables.next()) if(tables.getString("TABLE_NAME").equalsIgnoreCase("safe_revoke_permissions")) oldTable=true;
            }
            if (oldTable) {
                try (var ps=c.prepareStatement("SELECT subject_id,permission_name FROM safe_revoke_permissions"); var rs=ps.executeQuery()) {
                    while(rs.next()) {
                        String subject=rs.getString(1);
                        if(!subject.startsWith("dibsly:user:")) continue;
                        long id=Long.parseLong(subject.substring(12));
                        Permission permission=Permission.valueOf(rs.getString(2));
                        if(!revoked(c,id,permission)) {
                            try(var insert=c.prepareStatement("INSERT INTO permission_revocations(user_id,permission) SELECT id,? FROM users WHERE id=?")) {
                                insert.setString(1,permission.name());insert.setLong(2,id);insert.executeUpdate();
                            }
                        }
                    }
                }
            }
            try(var ps=c.prepareStatement("INSERT INTO app_migrations(name) VALUES('native-authorization-v1')")) {ps.executeUpdate();}
            return null;
        });
    }

    @FunctionalInterface private interface SqlWork<T> { T run(Connection c) throws SQLException; }
    private <T> T transaction(SqlWork<T> work) {
        try(Connection c=connection()) {
            c.setTransactionIsolation(Connection.TRANSACTION_READ_COMMITTED);c.setAutoCommit(false);
            try { T result=work.run(c);c.commit();return result; }
            catch(SQLException|RuntimeException|Error ex) {try {c.rollback();} catch(SQLException rollback) {ex.addSuppressed(rollback);} throw ex;}
        } catch(SQLException ex) {throw new DataAccessException("The database operation could not be confirmed. Refresh before retrying.",ex);}
    }

    public Optional<UserAccount> currentUser(long id) {
        try (Connection c = connection()) { return account(c, id, false); }
        catch (SQLException ex) { throw new DataAccessException("Could not refresh account access.", ex); }
    }

    private Optional<UserAccount> account(Connection c, long id, boolean lock) throws SQLException {
        try (PreparedStatement ps = c.prepareStatement("SELECT id,username,display_name,role,enabled FROM users WHERE id=?" + (lock ? " FOR UPDATE" : ""))) {
            ps.setLong(1, id);
            try (ResultSet rs = ps.executeQuery()) {
                if (!rs.next() || !rs.getBoolean("enabled")) return Optional.empty();
                return Optional.of(new UserAccount(rs.getLong("id"), rs.getString("username"), rs.getString("display_name"), Role.valueOf(rs.getString("role"))));
            }
        }
    }

    public Set<Permission> revoked(long userId) {
        Set<Permission> result=EnumSet.noneOf(Permission.class);
        try(Connection c=connection();var ps=c.prepareStatement("SELECT permission FROM permission_revocations WHERE user_id=?")) {
            ps.setLong(1,userId);try(var rs=ps.executeQuery()) {while(rs.next()) result.add(Permission.valueOf(rs.getString(1)));}
            return result;
        } catch(SQLException ex) {throw new DataAccessException("Could not load account permissions.",ex);}
    }
    private boolean revoked(Connection c,long id,Permission permission) throws SQLException {
        try(var ps=c.prepareStatement("SELECT permission FROM permission_revocations WHERE user_id=? AND permission=?")) {
            ps.setLong(1,id);ps.setString(2,permission.name());try(var rs=ps.executeQuery()) {return rs.next();}
        }
    }
    public boolean allowed(UserAccount user, Permission action) {
        if(user==null) return false;
        try(Connection c=connection()) {
            var actor=account(c,user.id(),false);
            return actor.isPresent() && actor.get().can(action) && !revoked(c,user.id(),action);
        } catch(SQLException ex) {throw new DataAccessException("Could not check account access.",ex);}
    }
    private static final class PermissionDenied extends RuntimeException {
        final String reason;
        PermissionDenied(String reason) {this.reason=reason;}
    }
    @FunctionalInterface private interface Write<T> { T run(Connection c, UserAccount actor) throws SQLException; }

    /** Application-owned authorization. Lock the current account until its protected work commits. */
    private <T> T authorized(UserAccount user, Permission action, Write<T> write) {
        if(user==null) throw new AuthorizationException("Sign in to continue.");
        try {
            return transaction(c -> {
                UserAccount actor=account(c,user.id(),true).orElseThrow(() -> new PermissionDenied("ACCOUNT_UNAVAILABLE"));
                if(!actor.can(action)) throw new PermissionDenied("NOT_GRANTED");
                if(revoked(c,actor.id(),action)) throw new PermissionDenied("REVOKED");
                T value=write.run(c,actor);
                if(action!=Permission.VIEW_OWN_REQUESTS && action!=Permission.VIEW_OPEN_REQUESTS) {
                    accessAudit(c,actor.id(),action,true,"ALLOWED");
                    audit(c,actor.username(),action.name(),"Action completed");
                }
                return value;
            });
        } catch(PermissionDenied ex) {
            transaction(c -> {accessAudit(c,user.id(),action,false,ex.reason);audit(c,user.username(),"DENIED",action.name()+" / "+ex.reason);return null;});
            throw new AuthorizationException("Permission denied: "+action.name()+" ("+ex.reason+"). Contact your administrator.");
        } catch(AuthorizationException ex) {
            transaction(c -> {audit(c,user.username(),"DENIED",action.name()+" / RESOURCE_ACCESS_DENIED");return null;});
            throw ex;
        }
    }
    private void accessAudit(Connection c,long id,Permission action,boolean allowed,String reason) throws SQLException {
        try(var ps=c.prepareStatement("INSERT INTO authorization_events(user_id,permission_name,allowed,reason,occurred_ms) VALUES(?,?,?,?,?)")) {
            ps.setLong(1,id);ps.setString(2,action.name());ps.setBoolean(3,allowed);ps.setString(4,reason);ps.setLong(5,System.currentTimeMillis());ps.executeUpdate();
        }
    }

    private void audit(Connection c, String actor, String action, String detail) throws SQLException {
        try (PreparedStatement ps = c.prepareStatement("INSERT INTO audit_events(actor,action,detail,created_at) VALUES(?,?,?,?)")) {
            ps.setString(1, actor); ps.setString(2, action); ps.setString(3, detail); ps.setObject(4, LocalDateTime.now()); ps.executeUpdate();
        }
    }

    public long post(UserAccount user, String category, String description, String urgency, BigDecimal budget) {
        return authorized(user, Permission.POST_REQUEST, (c, actor) -> insertRequest(c, actor.id(), actor.displayName(), category, description, urgency, budget));
    }

    private ServiceRequest lockedRequest(Connection c, long id, UserAccount actor, boolean owned) throws SQLException {
        try (PreparedStatement ps = c.prepareStatement("SELECT * FROM service_requests WHERE id=? FOR UPDATE")) {
            ps.setLong(1, id);
            try (ResultSet rs = ps.executeQuery()) {
                if (!rs.next()) throw new IllegalArgumentException("This project could not be found.");
                if (owned && actor.role() != Role.ADMIN && rs.getLong("customer_user_id") != actor.id())
                    throw new AuthorizationException("Only the client who posted this project can manage it.");
                return mapRequest(rs);
            }
        }
    }

    public void propose(UserAccount user, long requestId, String scope, BigDecimal price, int days, int support) {
        authorized(user, Permission.SUBMIT_PROPOSAL, (c, actor) -> {
            ServiceRequest request = lockedRequest(c, requestId, actor, false);
            if (request.status() != RequestStatus.OPEN) throw new IllegalArgumentException("This project is no longer accepting pitches.");
            try (PreparedStatement ps = c.prepareStatement("SELECT COUNT(*) FROM proposals WHERE request_id=? AND provider_user_id=? AND status<>'WITHDRAWN'")) {
                ps.setLong(1, requestId); ps.setLong(2, actor.id());
                try (ResultSet rs = ps.executeQuery()) { rs.next(); if (rs.getInt(1) > 0) throw new IllegalArgumentException("You have already pitched for this project."); }
            }
            insertProposal(c, requestId, actor.id(), actor.displayName(), scope, price, days, support);
            return null;
        });
    }

    public void accept(UserAccount user, long requestId, long proposalId, LocalDate date) {
        authorized(user, Permission.ACCEPT_PROPOSAL, (c, actor) -> {
            ServiceRequest request = lockedRequest(c, requestId, actor, true);
            if (request.status() != RequestStatus.OPEN) throw new IllegalArgumentException("This project has already been hired or closed.");
            try (PreparedStatement ps = c.prepareStatement("SELECT id FROM proposals WHERE id=? AND request_id=? AND status='PENDING'")) {
                ps.setLong(1, proposalId); ps.setLong(2, requestId);
                try (ResultSet rs = ps.executeQuery()) { if (!rs.next()) throw new IllegalArgumentException("Choose an available pitch for this project."); }
            }
            try (PreparedStatement ps = c.prepareStatement("INSERT INTO bookings(request_id,proposal_id,scheduled_for,status) VALUES(?,?,?,'CONFIRMED')")) {
                ps.setLong(1, requestId); ps.setLong(2, proposalId); ps.setObject(3, date); ps.executeUpdate();
            }
            try (PreparedStatement ps = c.prepareStatement("UPDATE service_requests SET status='BOOKED' WHERE id=?")) { ps.setLong(1, requestId); ps.executeUpdate(); }
            try (PreparedStatement ps = c.prepareStatement("UPDATE proposals SET status=CASE WHEN id=? THEN 'ACCEPTED' ELSE 'REJECTED' END WHERE request_id=? AND status='PENDING'")) {
                ps.setLong(1, proposalId); ps.setLong(2, requestId); ps.executeUpdate();
            }
            return null;
        });
    }

    public void transition(UserAccount user, long requestId, boolean complete) {
        authorized(user, Permission.MANAGE_REQUEST, (c, actor) -> {
            ServiceRequest request = lockedRequest(c, requestId, actor, true);
            if (request.status() != (complete ? RequestStatus.BOOKED : RequestStatus.OPEN))
                throw new IllegalArgumentException(complete ? "Only an active contract can be completed." : "Only an open project can be cancelled.");
            try (PreparedStatement ps = c.prepareStatement("UPDATE service_requests SET status=? WHERE id=?")) {
                ps.setString(1, complete ? "COMPLETED" : "CANCELLED"); ps.setLong(2, requestId); ps.executeUpdate();
            }
            if (complete) {
                try (PreparedStatement ps = c.prepareStatement("UPDATE bookings SET status='COMPLETED' WHERE request_id=?")) { ps.setLong(1, requestId); ps.executeUpdate(); }
            } else {
                try (PreparedStatement ps = c.prepareStatement("UPDATE proposals SET status='REJECTED' WHERE request_id=? AND status='PENDING'")) { ps.setLong(1, requestId); ps.executeUpdate(); }
            }
            return null;
        });
    }

    public void withdraw(UserAccount user, long requestId, long proposalId) {
        authorized(user, Permission.WITHDRAW_PROPOSAL, (c, actor) -> {
            lockedRequest(c, requestId, actor, false);
            try (PreparedStatement ps = c.prepareStatement("UPDATE proposals SET status='WITHDRAWN' WHERE id=? AND request_id=? AND provider_user_id=? AND status='PENDING'")) {
                ps.setLong(1, proposalId); ps.setLong(2, requestId); ps.setLong(3, actor.id());
                if (ps.executeUpdate() != 1) throw new IllegalArgumentException("Only your own pending pitch can be withdrawn.");
            }
            return null;
        });
    }

    public List<ServiceRequest> browse(String query, String category, String sort, int page) {
        String order = "budget".equals(sort) ? "budget DESC,id DESC" : "id DESC";
        String sql = "SELECT * FROM service_requests WHERE status='OPEN' AND (?='' OR category=?) AND LOWER(description) LIKE ? ESCAPE '!' ORDER BY " + order + " LIMIT 13 OFFSET ?";
        List<ServiceRequest> result = new ArrayList<>();
        try (Connection c = connection(); PreparedStatement ps = c.prepareStatement(sql)) {
            ps.setString(1, category); ps.setString(2, category);
            ps.setString(3, "%" + query.toLowerCase(java.util.Locale.ROOT).replace("!", "!!").replace("%", "!%").replace("_", "!_") + "%");
            ps.setInt(4, (page - 1) * 12);
            try (ResultSet rs = ps.executeQuery()) { while (rs.next()) result.add(mapRequest(rs)); }
            return result;
        } catch (SQLException ex) { throw new DataAccessException("Could not load projects.", ex); }
    }

    private Permission readPermission(UserAccount user) {
        if (user == null) throw new AuthorizationException("Sign in to continue.");
        UserAccount actual = currentUser(user.id()).orElseThrow(() -> new AuthorizationException("Your account is unavailable."));
        return actual.role() == Role.CUSTOMER ? Permission.VIEW_OWN_REQUESTS : Permission.VIEW_OPEN_REQUESTS;
    }

    public List<ServiceRequest> workspace(UserAccount user) {
        return authorized(user, readPermission(user), (c, actor) -> {
            if (actor.role() == Role.ADMIN) return queryRequests(c, "SELECT * FROM service_requests ORDER BY id DESC LIMIT 100", null);
            if (actor.role() == Role.CUSTOMER) return queryRequests(c, "SELECT * FROM service_requests WHERE customer_user_id=? ORDER BY id DESC LIMIT 100", actor.id());
            return queryRequests(c, "SELECT * FROM service_requests WHERE id IN (SELECT request_id FROM proposals WHERE provider_user_id=?) ORDER BY id DESC LIMIT 100", actor.id());
        });
    }

    public List<Proposal> visibleProposals(UserAccount user, long requestId) {
        return authorized(user, readPermission(user), (c, actor) -> {
            boolean owner = actor.role() == Role.ADMIN || requestOwnedBy(c, requestId, actor.id());
            List<Proposal> result = new ArrayList<>();
            String sql = "SELECT * FROM proposals WHERE request_id=?" + (owner ? "" : " AND provider_user_id=?") + " ORDER BY price,id LIMIT 100";
            try (PreparedStatement ps = c.prepareStatement(sql)) {
                ps.setLong(1, requestId); if (!owner) ps.setLong(2, actor.id());
                try (ResultSet rs = ps.executeQuery()) { while (rs.next()) result.add(mapProposal(rs)); }
            }
            return result;
        });
    }

    public List<UserAccount> users(UserAccount actor) {
        if (!allowed(actor, Permission.ADMINISTER)) throw new AuthorizationException("Administrator access is required.");
        List<UserAccount> result = new ArrayList<>();
        try (Connection c = connection(); Statement s = c.createStatement(); ResultSet rs = s.executeQuery("SELECT id,username,display_name,role FROM users ORDER BY id LIMIT 100")) {
            while (rs.next()) result.add(new UserAccount(rs.getLong(1), rs.getString(2), rs.getString(3), Role.valueOf(rs.getString(4))));
            return result;
        } catch (SQLException ex) { throw new DataAccessException("Could not load accounts.", ex); }
    }

    public void setRevoked(UserAccount admin, long target, Permission permission, boolean revoke) {
        authorized(admin, Permission.ADMINISTER, (c, actor) -> {
            UserAccount subject = account(c, target, true).orElseThrow(() -> new IllegalArgumentException("Account not found."));
            if (subject.role() == Role.ADMIN || !subject.can(permission)) throw new IllegalArgumentException("Choose an existing client or freelancer permission.");
            boolean current=revoked(c,target,permission);
            if(current!=revoke) {
                String sql=revoke ? "INSERT INTO permission_revocations(user_id,permission) VALUES(?,?)" : "DELETE FROM permission_revocations WHERE user_id=? AND permission=?";
                try(var ps=c.prepareStatement(sql)) {ps.setLong(1,target);ps.setString(2,permission.name());ps.executeUpdate();}
            }
            audit(c,actor.username(),revoke ? "REVOKED" : "RESTORED",subject.username()+" / "+permission.name()+(current==revoke ? " / unchanged" : ""));
            return null;
        });
    }

    public List<AuditEvent> auditEvents(UserAccount actor) {
        if (!allowed(actor, Permission.ADMINISTER)) throw new AuthorizationException("Administrator access is required.");
        List<AuditEvent> result = new ArrayList<>();
        try (Connection c = connection(); Statement s = c.createStatement(); ResultSet rs = s.executeQuery("SELECT * FROM audit_events ORDER BY id DESC LIMIT 60")) {
            while (rs.next()) result.add(new AuditEvent(rs.getLong("id"), rs.getString("actor"), rs.getString("action"), rs.getString("detail"), rs.getObject("created_at", LocalDateTime.class)));
            return result;
        } catch (SQLException ex) { throw new DataAccessException("Could not read the audit trail.", ex); }
    }

    private void seed(Connection c) throws SQLException {
        long ac = insertRequest(c, null, "Aarav Mehta", "Home Appliances", "AC runs but the room is not cooling.", "Within 24 hours", new BigDecimal("4500"));
        long laptop = insertRequest(c, null, "Diya Rao", "Computer Repair", "Laptop overheats and shuts down during classes.", "This week", new BigDecimal("7000"));
        insertProposal(c, ac, null, "CoolCare Services", "Likely refrigerant leak; pressure test and refill included.", new BigDecimal("2800"), 1, 90);
        insertProposal(c, ac, null, "ArcticFix", "Indoor coil inspection, deep clean and gas-level correction.", new BigDecimal("2400"), 2, 60);
        insertProposal(c, laptop, null, "ByteWorks", "Thermal service with fan test and new thermal compound.", new BigDecimal("2200"), 2, 30);
    }

    private long insertRequest(Connection c, Long customerId, String customer, String category, String description,
            String urgency, BigDecimal budget) throws SQLException {
        String sql = "INSERT INTO service_requests(customer_user_id,customer_name,category,description,urgency,budget,status,created_at) VALUES(?,?,?,?,?,?,'OPEN',?)";
        try (PreparedStatement ps = c.prepareStatement(sql, Statement.RETURN_GENERATED_KEYS)) {
            nullableLong(ps, 1, customerId); ps.setString(2, customer); ps.setString(3, category);
            ps.setString(4, description); ps.setString(5, urgency); ps.setBigDecimal(6, budget);
            ps.setObject(7, LocalDateTime.now()); ps.executeUpdate();
            try (ResultSet keys = ps.getGeneratedKeys()) { keys.next(); return keys.getLong(1); }
        }
    }

    private void insertProposal(Connection c, long requestId, Long providerId, String provider, String diagnosis,
            BigDecimal price, int eta, int warranty) throws SQLException {
        String sql = "INSERT INTO proposals(request_id,provider_user_id,provider_name,diagnosis,price,eta_days,warranty_days,status,created_at) VALUES(?,?,?,?,?,?,?,'PENDING',?)";
        try (PreparedStatement ps = c.prepareStatement(sql)) {
            ps.setLong(1, requestId); nullableLong(ps, 2, providerId); ps.setString(3, provider);
            ps.setString(4, diagnosis); ps.setBigDecimal(5, price); ps.setInt(6, eta);
            ps.setInt(7, warranty); ps.setObject(8, LocalDateTime.now()); ps.executeUpdate();
        }
    }

    private void nullableLong(PreparedStatement ps, int index, Long value) throws SQLException {
        if (value == null) ps.setNull(index, java.sql.Types.BIGINT); else ps.setLong(index, value);
    }

    public long createRequest(String customer, String category, String description, String urgency, BigDecimal budget) {
        return createRequest(null, customer, category, description, urgency, budget);
    }

    public long createRequest(Long customerId, String customer, String category, String description, String urgency, BigDecimal budget) {
        try (Connection c = connection()) { return insertRequest(c, customerId, customer, category, description, urgency, budget); }
        catch (SQLException ex) { throw new DataAccessException("Could not save the request.", ex); }
    }

    public void createProposal(long requestId, String provider, String diagnosis, BigDecimal price, int eta, int warranty) {
        createProposal(requestId, null, provider, diagnosis, price, eta, warranty);
    }

    public void createProposal(long requestId, Long providerId, String provider, String diagnosis, BigDecimal price, int eta, int warranty) {
        try (Connection c = connection()) { insertProposal(c, requestId, providerId, provider, diagnosis, price, eta, warranty); }
        catch (SQLException ex) { throw new DataAccessException("Could not save the proposal.", ex); }
    }

    public List<ServiceRequest> findRequests() { return queryRequests("SELECT * FROM service_requests ORDER BY created_at DESC", null); }

    public List<ServiceRequest> findRequestsForCustomer(long customerId) {
        return queryRequests("SELECT * FROM service_requests WHERE customer_user_id=? ORDER BY created_at DESC", customerId);
    }

    private List<ServiceRequest> queryRequests(String sql, Long customerId) {
        try (Connection c = connection()) { return queryRequests(c, sql, customerId); }
        catch (SQLException ex) { throw new DataAccessException("Could not load requests.", ex); }
    }

    private List<ServiceRequest> queryRequests(Connection c, String sql, Long customerId) throws SQLException {
        List<ServiceRequest> result = new ArrayList<>();
        try (PreparedStatement ps = c.prepareStatement(sql)) {
            if (customerId != null) ps.setLong(1, customerId);
            try (ResultSet rs = ps.executeQuery()) { while (rs.next()) result.add(mapRequest(rs)); }
            return result;
        }
    }

    public Optional<ServiceRequest> findRequest(long id) {
        try (Connection c = connection(); PreparedStatement ps = c.prepareStatement("SELECT * FROM service_requests WHERE id=?")) {
            ps.setLong(1, id);
            try (ResultSet rs = ps.executeQuery()) { return rs.next() ? Optional.of(mapRequest(rs)) : Optional.empty(); }
        } catch (SQLException ex) { throw new DataAccessException("Could not load the request.", ex); }
    }

    public boolean requestOwnedBy(long requestId, long customerId) {
        try (Connection c = connection()) { return requestOwnedBy(c, requestId, customerId); }
        catch (SQLException ex) { throw new DataAccessException("Could not verify request ownership.", ex); }
    }
    private boolean requestOwnedBy(Connection c, long requestId, long customerId) throws SQLException {
        try (PreparedStatement ps = c.prepareStatement("SELECT COUNT(*) FROM service_requests WHERE id=? AND customer_user_id=?")) {
            ps.setLong(1, requestId); ps.setLong(2, customerId);
            try (ResultSet rs = ps.executeQuery()) { rs.next(); return rs.getLong(1) == 1; }
        }
    }

    public List<Proposal> findProposals(long requestId) {
        List<Proposal> result = new ArrayList<>();
        try (Connection c = connection(); PreparedStatement ps = c.prepareStatement("SELECT * FROM proposals WHERE request_id=? ORDER BY created_at DESC")) {
            ps.setLong(1, requestId);
            try (ResultSet rs = ps.executeQuery()) { while (rs.next()) result.add(mapProposal(rs)); }
            return result;
        } catch (SQLException ex) { throw new DataAccessException("Could not load proposals.", ex); }
    }

    public Optional<Proposal> findProposal(long proposalId) {
        try (Connection c = connection(); PreparedStatement ps = c.prepareStatement("SELECT * FROM proposals WHERE id=?")) {
            ps.setLong(1, proposalId);
            try (ResultSet rs = ps.executeQuery()) { return rs.next() ? Optional.of(mapProposal(rs)) : Optional.empty(); }
        } catch (SQLException ex) { throw new DataAccessException("Could not load the proposal.", ex); }
    }

    public void book(long requestId, long proposalId, LocalDate date) {
        try (Connection c = connection()) {
            c.setAutoCommit(false);
            try (PreparedStatement insert = c.prepareStatement("INSERT INTO bookings(request_id,proposal_id,scheduled_for,status) VALUES(?,?,?,'CONFIRMED')");
                 PreparedStatement request = c.prepareStatement("UPDATE service_requests SET status='BOOKED' WHERE id=? AND status='OPEN'");
                 PreparedStatement proposal = c.prepareStatement("UPDATE proposals SET status=CASE WHEN id=? THEN 'ACCEPTED' ELSE 'REJECTED' END WHERE request_id=?")) {
                insert.setLong(1, requestId); insert.setLong(2, proposalId); insert.setObject(3, date); insert.executeUpdate();
                request.setLong(1, requestId);
                if (request.executeUpdate() != 1) throw new SQLException("Request is no longer available.");
                proposal.setLong(1, proposalId); proposal.setLong(2, requestId); proposal.executeUpdate();
                c.commit();
            } catch (SQLException ex) { c.rollback(); throw ex; }
        } catch (SQLException ex) { throw new DataAccessException("Could not confirm the booking.", ex); }
    }

    public List<Booking> findBookings() {
        String sql = "SELECT b.id,b.request_id,b.proposal_id,p.provider_name,r.category,b.scheduled_for,b.status FROM bookings b JOIN proposals p ON p.id=b.proposal_id JOIN service_requests r ON r.id=b.request_id ORDER BY b.id DESC";
        List<Booking> result = new ArrayList<>();
        try (Connection c = connection(); Statement s = c.createStatement(); ResultSet rs = s.executeQuery(sql)) {
            while (rs.next()) result.add(new Booking(rs.getLong(1),rs.getLong(2),rs.getLong(3),rs.getString(4),rs.getString(5),rs.getObject(6,LocalDate.class),rs.getString(7)));
            return result;
        } catch (SQLException ex) { throw new DataAccessException("Could not load bookings.", ex); }
    }

    public DashboardStats stats() {
        try (Connection c = connection(); Statement s = c.createStatement()) {
            long open = scalar(s, "SELECT COUNT(*) FROM service_requests WHERE status='OPEN'");
            long proposals = scalar(s, "SELECT COUNT(*) FROM proposals");
            long bookings = scalar(s, "SELECT COUNT(*) FROM bookings");
            long completed = scalar(s, "SELECT COUNT(*) FROM service_requests WHERE status='COMPLETED'");
            return new DashboardStats(open, proposals, bookings, completed);
        } catch (SQLException ex) { throw new DataAccessException("Could not load dashboard metrics.", ex); }
    }

    public long userCount() {
        try (Connection c = connection(); Statement s = c.createStatement()) { return scalar(s, "SELECT COUNT(*) FROM users"); }
        catch (SQLException ex) { throw new DataAccessException("Could not count users.", ex); }
    }

    public long createUser(String username, String displayName, byte[] hash, byte[] salt, int iterations, Role role) {
        String sql = "INSERT INTO users(username,display_name,password_hash,password_salt,password_iterations,role,enabled,created_at) VALUES(?,?,?,?,?,?,TRUE,?)";
        return transaction(c -> {
                long id;
                try (PreparedStatement ps = c.prepareStatement(sql, Statement.RETURN_GENERATED_KEYS)) {
                    ps.setString(1, username); ps.setString(2, displayName); ps.setBytes(3, hash); ps.setBytes(4, salt);
                    ps.setInt(5, iterations); ps.setString(6, role.name()); ps.setObject(7, LocalDateTime.now()); ps.executeUpdate();
                    try (ResultSet keys = ps.getGeneratedKeys()) { keys.next(); id = keys.getLong(1); }
                }
                return id;
            });
    }

    public Optional<UserCredentials> findCredentials(String username) {
        String sql = "SELECT * FROM users WHERE LOWER(username)=LOWER(?)";
        try (Connection c = connection(); PreparedStatement ps = c.prepareStatement(sql)) {
            ps.setString(1, username);
            try (ResultSet rs = ps.executeQuery()) {
                if (!rs.next()) return Optional.empty();
                UserAccount account = new UserAccount(rs.getLong("id"), rs.getString("username"),
                        rs.getString("display_name"), Role.valueOf(rs.getString("role")));
                return Optional.of(new UserCredentials(account, rs.getBytes("password_hash"),
                        rs.getBytes("password_salt"), rs.getInt("password_iterations"), rs.getBoolean("enabled")));
            }
        } catch (SQLException ex) { throw new DataAccessException("Could not load the account.", ex); }
    }

    private long scalar(Statement s, String sql) throws SQLException { try (ResultSet rs = s.executeQuery(sql)) { rs.next(); return rs.getLong(1); } }
    private ServiceRequest mapRequest(ResultSet rs) throws SQLException { return new ServiceRequest(rs.getLong("id"),rs.getString("customer_name"),rs.getString("category"),rs.getString("description"),rs.getString("urgency"),rs.getBigDecimal("budget"),RequestStatus.valueOf(rs.getString("status")),rs.getObject("created_at",LocalDateTime.class)); }
    private Proposal mapProposal(ResultSet rs) throws SQLException { return new Proposal(rs.getLong("id"),rs.getLong("request_id"),rs.getString("provider_name"),rs.getString("diagnosis"),rs.getBigDecimal("price"),rs.getInt("eta_days"),rs.getInt("warranty_days"),ProposalStatus.valueOf(rs.getString("status")),rs.getObject("created_at",LocalDateTime.class)); }
}
