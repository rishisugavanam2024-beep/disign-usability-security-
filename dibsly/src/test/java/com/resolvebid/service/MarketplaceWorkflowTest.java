package com.resolvebid.service;

import static org.junit.jupiter.api.Assertions.*;
import java.nio.file.Path;
import java.time.LocalDate;
import java.util.*;
import java.util.concurrent.*;
import org.junit.jupiter.api.*;
import org.junit.jupiter.api.io.TempDir;
import com.resolvebid.dao.DatabaseManager;
import com.resolvebid.exception.*;
import com.resolvebid.model.*;
import com.resolvebid.util.FileService;

class MarketplaceWorkflowTest {
    @TempDir Path temp;
    DatabaseManager db; MarketplaceService service;
    UserAccount client, otherClient, freelancer, competitor, admin;
    String jdbc;
    @BeforeEach void setUp() {
        jdbc = "jdbc:h2:mem:" + UUID.randomUUID() + ";DB_CLOSE_DELAY=-1;MODE=MySQL";
        db = new DatabaseManager(jdbc, "sa", ""); db.initialize();
        service = new MarketplaceService(db, new FileService(temp), new ValueRankingStrategy());
        client = user("client", Role.CUSTOMER); otherClient = user("other", Role.CUSTOMER);
        freelancer = user("freelancer", Role.PROVIDER); competitor = user("competitor", Role.PROVIDER); admin = user("admin", Role.ADMIN);
    }
    UserAccount user(String name, Role role) {
        long id = db.createUser(name, name, new byte[32], new byte[16], 210000, role);
        return new UserAccount(id, name, name, role);
    }
    ServiceRequest project() throws Exception {
        return service.request(service.postRequest(client, "Development & IT", "Build a thoughtful Java application\nInclude clear documentation and tests.", "This week", "20000"));
    }
    void pitch(UserAccount user, ServiceRequest project) throws Exception { service.submitProposal(user, project, "A detailed delivery plan with documentation and tests", "18000", "10", "14"); }
    @Test void clientCannotPitchAndFreelancerCannotPost() throws Exception {
        ServiceRequest p = project();
        assertThrows(AuthorizationException.class, () -> pitch(client, p));
        assertThrows(AuthorizationException.class, () -> service.postRequest(freelancer, "Development & IT", "A valid project description", "Flexible", "100"));
    }
    @Test void storedRoleOverridesForgedSessionRole() throws Exception {
        UserAccount forged = new UserAccount(freelancer.id(), "admin", "admin", Role.ADMIN);
        assertThrows(AuthorizationException.class, () -> db.setRevoked(forged, client.id(), Permission.POST_REQUEST, true));
    }
    @Test void accountAuditIsRestrictedToStoredAdministratorRole() throws Exception {
        ServiceRequest p=project();db.setRevoked(admin,freelancer.id(),Permission.SUBMIT_PROPOSAL,true);
        assertThrows(AuthorizationException.class,()->pitch(freelancer,p));
        var forged=new UserAccount(freelancer.id(),"admin","admin",Role.ADMIN);
        assertThrows(AuthorizationException.class,()->db.auditEvents(forged));
        assertTrue(db.auditEvents(admin).stream().anyMatch(e->e.action().equals("DENIED")&&e.detail().contains("REVOKED")));
    }
    @Test void pitchesStayPrivateBetweenFreelancers() throws Exception {
        ServiceRequest p = project(); pitch(freelancer, p); pitch(competitor, p);
        assertEquals(2, service.proposalsFor(client, p.id()).size());
        assertEquals(1, service.proposalsFor(freelancer, p.id()).size());
        assertEquals("freelancer", service.proposalsFor(freelancer, p.id()).getFirst().providerName());
        assertTrue(service.proposalsFor(otherClient, p.id()).isEmpty());
    }
    @Test void onlyOwnerCanAcceptOrClose() throws Exception {
        ServiceRequest p = project(); pitch(freelancer, p); Proposal offer = db.findProposals(p.id()).getFirst();
        assertThrows(AuthorizationException.class, () -> service.acceptProposal(otherClient, p, offer, LocalDate.now()));
        assertThrows(AuthorizationException.class, () -> service.transition(otherClient, p.id(), false));
    }
    @Test void revocationRejectsExistingSessionAndSurvivesNewDatabaseInstance() throws Exception {
        ServiceRequest p = project();
        db.setRevoked(admin, freelancer.id(), Permission.SUBMIT_PROPOSAL, true);
        assertThrows(AuthorizationException.class, () -> pitch(freelancer, p));
        DatabaseManager other = new DatabaseManager(jdbc, "sa", ""); other.initialize();
        assertFalse(other.allowed(freelancer, Permission.SUBMIT_PROPOSAL));
        assertTrue(db.findProposals(p.id()).isEmpty());
        db.setRevoked(admin, freelancer.id(), Permission.SUBMIT_PROPOSAL, false);
        pitch(freelancer, p); assertEquals(1, db.findProposals(p.id()).size());
        assertTrue(db.auditEvents(admin).stream().anyMatch(e -> e.action().equals("DENIED")));
    }
    @Test void restorationCannotGrantPermissionsOutsideStoredRole() throws Exception {
        ServiceRequest p = project();
        assertThrows(IllegalArgumentException.class, () -> db.setRevoked(admin, client.id(), Permission.SUBMIT_PROPOSAL, false));
        assertThrows(AuthorizationException.class, () -> pitch(client, p));
    }
    @Test void duplicatePitchIsRejectedButWithdrawnPitchCanBeReplaced() throws Exception {
        ServiceRequest p = project(); pitch(freelancer, p);
        assertThrows(IllegalArgumentException.class, () -> pitch(freelancer, p));
        Proposal offer = db.findProposals(p.id()).getFirst();
        assertThrows(IllegalArgumentException.class, () -> service.withdraw(competitor, p.id(), offer.id()));
        service.withdraw(freelancer, p.id(), offer.id()); pitch(freelancer, p);
        assertEquals(1, db.findProposals(p.id()).stream().filter(x -> x.status()==ProposalStatus.PENDING).count());
    }
    @Test void cancelledProjectRejectsStalePitchAndRemainsPrivate() throws Exception {
        ServiceRequest p = project(); service.transition(client, p.id(), false);
        assertThrows(IllegalArgumentException.class, () -> pitch(freelancer, p));
        assertThrows(AuthorizationException.class, () -> service.requestFor(otherClient, p.id()));
        assertTrue(service.browse("", "", "", 1).isEmpty());
    }
    @Test void acceptanceCreatesOneContractAndCanBeCompleted() throws Exception {
        ServiceRequest p = project(); pitch(freelancer, p); pitch(competitor, p);
        Proposal offer = db.findProposals(p.id()).getFirst();
        service.acceptProposal(client, p, offer, LocalDate.now());
        assertEquals(RequestStatus.BOOKED, service.request(p.id()).status());
        assertEquals(1, db.findBookings().size());
        assertEquals(1, db.findProposals(p.id()).stream().filter(x -> x.status()==ProposalStatus.ACCEPTED).count());
        assertThrows(IllegalArgumentException.class, () -> service.acceptProposal(client, p, offer, LocalDate.now()));
        service.transition(client, p.id(), true);
        assertEquals(RequestStatus.COMPLETED, service.request(p.id()).status());
        assertEquals("COMPLETED", db.findBookings().getFirst().status());
    }
    @Test void concurrentAcceptsCannotCreateTwoContracts() throws Exception {
        ServiceRequest p = project(); pitch(freelancer, p); pitch(competitor, p);
        List<Proposal> offers = db.findProposals(p.id()); CountDownLatch go = new CountDownLatch(1);
        try (ExecutorService pool = Executors.newFixedThreadPool(2)) {
            List<Future<Boolean>> results = new ArrayList<>();
            for (Proposal offer : offers) results.add(pool.submit(() -> { go.await(); try { service.acceptProposal(client, p, offer, LocalDate.now()); return true; } catch (IllegalArgumentException ex) { return false; } }));
            go.countDown(); int successes=0; for (Future<Boolean> result:results) if(result.get(10, TimeUnit.SECONDS)) successes++;
            assertEquals(1, successes); assertEquals(1, db.findBookings().size());
        }
    }
    @Test void invalidAmountsDatesAndLengthsAreRejected() throws Exception {
        ServiceRequest p = project();
        for(String amount:List.of("0", "-1", "0.001", "1e12", "NaN")) assertThrows(ValidationException.class, () -> service.submitProposal(freelancer, p, "A legitimate project plan", amount, "10", "14"));
        assertThrows(ValidationException.class, () -> service.submitProposal(freelancer, p, "x".repeat(1001), "100", "10", "14"));
        assertThrows(ValidationException.class, () -> service.submitProposal(freelancer, p, "A legitimate project plan", "100", "366", "14"));
        pitch(freelancer,p); assertThrows(ValidationException.class, () -> service.acceptProposal(client,p,db.findProposals(p.id()).getFirst(),LocalDate.now().minusDays(1)));
    }
    @Test void searchesAreLiteralAndPaginationIsBounded() throws Exception {
        for(int i=0;i<15;i++) project();
        assertEquals(13, service.browse("", "", "", 1).size());
        assertEquals(3, service.browse("", "", "", 2).size());
        assertTrue(service.browse("%", "", "", 1).isEmpty());
        assertTrue(service.browse("", "Marketing", "", 1).isEmpty());
    }
    @Test void revokedReadPermissionBlocksWorkspaceAndApiSource() throws Exception {
        project(); db.setRevoked(admin, client.id(), Permission.VIEW_OWN_REQUESTS, true);
        assertThrows(AuthorizationException.class, () -> service.requestsFor(client));
    }
    @Test void existingRestrictionsAndRestorationSurviveRestart() throws Exception {
        db.setRevoked(admin,freelancer.id(),Permission.SUBMIT_PROPOSAL,true);
        DatabaseManager restarted=new DatabaseManager(jdbc,"sa","");restarted.initialize();
        assertFalse(restarted.allowed(freelancer,Permission.SUBMIT_PROPOSAL));
        restarted.setRevoked(admin,freelancer.id(),Permission.SUBMIT_PROPOSAL,false);
        restarted.initialize();assertTrue(restarted.allowed(freelancer,Permission.SUBMIT_PROPOSAL));
    }
    @Test void formerLibraryRestrictionsImportOnlyOnce() throws Exception {
        try(var c=java.sql.DriverManager.getConnection(jdbc,"sa","");var s=c.createStatement()) {
            s.execute("DELETE FROM app_migrations WHERE name='native-authorization-v1'");
            s.execute("CREATE TABLE safe_revoke_permissions(subject_id VARCHAR(128),permission_name VARCHAR(128))");
            s.execute("INSERT INTO safe_revoke_permissions VALUES('dibsly:user:"+freelancer.id()+"','SUBMIT_PROPOSAL')");
        }
        db.initialize();assertFalse(db.allowed(freelancer,Permission.SUBMIT_PROPOSAL));
        db.setRevoked(admin,freelancer.id(),Permission.SUBMIT_PROPOSAL,false);
        db.initialize();assertTrue(db.allowed(freelancer,Permission.SUBMIT_PROPOSAL));
    }
    @Test void nativeAuthorizationRecordsActualDeniedPermissionAndNoPitch() throws Exception {
        ServiceRequest p=project();db.setRevoked(admin,freelancer.id(),Permission.SUBMIT_PROPOSAL,true);
        var denied=assertThrows(AuthorizationException.class,()->pitch(freelancer,p));
        assertTrue(denied.getMessage().contains("REVOKED"));assertTrue(db.findProposals(p.id()).isEmpty());
        try(var c=java.sql.DriverManager.getConnection(jdbc,"sa","");var s=c.createStatement();var rs=s.executeQuery("SELECT COUNT(*) FROM authorization_events WHERE allowed=FALSE AND permission_name='SUBMIT_PROPOSAL' AND reason='REVOKED'")) {
            rs.next();assertEquals(1,rs.getInt(1));
        }
    }
    @Test void disabledAccountCannotWriteFromOldSession() throws Exception {
        ServiceRequest p=project();
        try(var c=java.sql.DriverManager.getConnection(jdbc,"sa","");var ps=c.prepareStatement("UPDATE users SET enabled=FALSE WHERE id=?")) {ps.setLong(1,freelancer.id());ps.executeUpdate();}
        assertThrows(AuthorizationException.class,()->pitch(freelancer,p));assertTrue(db.findProposals(p.id()).isEmpty());
    }
}
