package com.resolvebid.security;

import static org.junit.jupiter.api.Assertions.*;
import java.nio.file.Path;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;
import com.resolvebid.dao.DatabaseManager;
import com.resolvebid.exception.ValidationException;
import com.resolvebid.model.Role;

class AuthServiceTest {
    @TempDir Path temp;
    @Test void registersAndAuthenticatesWithRole() throws Exception {
        DatabaseManager database = new DatabaseManager(temp.resolve("auth")); database.initialize();
        AuthService auth = new AuthService(database);
        var created = auth.register("ravi.tech", "Ravi Tech", "StrongPass99!".toCharArray(), Role.PROVIDER);
        assertEquals(Role.PROVIDER, created.role());
        assertTrue(auth.authenticate("RAVI.TECH", "StrongPass99!".toCharArray()).isPresent());
        assertTrue(auth.authenticate("ravi.tech", "wrong-password".toCharArray()).isEmpty());
    }
    @Test void rejectsWeakPassword() throws Exception {
        DatabaseManager database = new DatabaseManager(temp.resolve("weak")); database.initialize();
        AuthService auth = new AuthService(database);
        assertThrows(ValidationException.class,
                () -> auth.register("customer", "Customer", "short".toCharArray(), Role.CUSTOMER));
    }
}
