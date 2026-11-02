package com.resolvebid.app;

import java.nio.file.Files;
import java.nio.file.Path;
import com.resolvebid.config.AppConfig;
import com.resolvebid.dao.DatabaseManager;
import com.resolvebid.model.UserAccount;
import com.resolvebid.security.AuthService;
import com.resolvebid.service.MarketplaceService;
import com.resolvebid.service.ValueRankingStrategy;
import com.resolvebid.ui.AppShell;
import com.resolvebid.ui.LoginView;
import com.resolvebid.util.AsyncTaskService;
import com.resolvebid.util.FileService;
import com.resolvebid.web.EmbeddedWebServer;
import javafx.application.Application;
import javafx.application.Platform;
import javafx.scene.Scene;
import javafx.stage.Stage;

public final class ResolveBidApp extends Application {
    private AsyncTaskService async;
    private EmbeddedWebServer webServer;
    private MarketplaceService marketplace;
    private AuthService auth;
    private AppConfig config;

    @Override public void start(Stage stage) throws Exception {
        config = AppConfig.load();
        Path data = Files.createDirectories(Path.of("data"));
        DatabaseManager database = new DatabaseManager(config.databaseUrl(), config.databaseUser(), config.databasePassword());
        database.initialize();
        auth = new AuthService(database); auth.bootstrapAdmin(config.adminUsername(), config.adminPassword());
        marketplace = new MarketplaceService(database, new FileService(data), new ValueRankingStrategy());
        async = new AsyncTaskService(); webServer = new EmbeddedWebServer(marketplace, auth, config);
        stage.setTitle("Dibsly · Smart Service Marketplace"); stage.setMinWidth(980); stage.setMinHeight(680);
        showLogin(stage); stage.show();
        Thread.ofPlatform().daemon().name("resolvebid-web").start(() -> {
            try { webServer.start(); }
            catch (Exception ex) { Platform.runLater(() -> System.err.println("Web service unavailable: " + ex.getMessage())); }
        });
    }

    private void showLogin(Stage stage) {
        LoginView login = new LoginView(auth, config, account -> showWorkspace(stage, account));
        stage.setScene(new Scene(login.root(), 1180, 760));
    }

    private void showWorkspace(Stage stage, UserAccount account) {
        AppShell shell = new AppShell(marketplace, async, account, () -> showLogin(stage));
        shell.setServerStatus("Web app: localhost:" + config.port(), true);
        stage.setScene(new Scene(shell.root(), 1280, 800));
    }

    @Override public void stop() { if (async != null) async.close(); if (webServer != null) webServer.close(); }
    public static void main(String[] args) { launch(args); }
}
