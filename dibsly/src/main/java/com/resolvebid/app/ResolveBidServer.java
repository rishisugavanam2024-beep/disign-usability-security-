package com.resolvebid.app;

import java.nio.file.Files;
import java.nio.file.Path;
import com.resolvebid.config.AppConfig;
import com.resolvebid.dao.DatabaseManager;
import com.resolvebid.security.AuthService;
import com.resolvebid.service.MarketplaceService;
import com.resolvebid.service.ValueRankingStrategy;
import com.resolvebid.util.FileService;
import com.resolvebid.web.EmbeddedWebServer;

public final class ResolveBidServer {
    private ResolveBidServer() { }
    public static void main(String[] args) throws Exception {
        AppConfig config = AppConfig.load();
        Path data = Files.createDirectories(Path.of("data"));
        DatabaseManager database = new DatabaseManager(config.databaseUrl(), config.databaseUser(), config.databasePassword());
        database.initialize();
        AuthService auth = new AuthService(database); auth.bootstrapAdmin(config.adminUsername(), config.adminPassword());
        com.resolvebid.service.DemoData.seed(database, auth);
        MarketplaceService marketplace = new MarketplaceService(database, new FileService(data), new ValueRankingStrategy());
        EmbeddedWebServer server = new EmbeddedWebServer(marketplace, auth, config);
        Runtime.getRuntime().addShutdownHook(Thread.ofPlatform().unstarted(server::close));
        server.start();
        System.out.println("Dibsly is ready on http://localhost:" + config.port());
        server.await();
    }
}
