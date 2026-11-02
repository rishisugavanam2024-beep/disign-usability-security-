package com.resolvebid.web;

import java.nio.file.Files;
import java.nio.file.Path;
import org.apache.catalina.Context;
import org.apache.catalina.filters.HttpHeaderSecurityFilter;
import org.apache.catalina.startup.Tomcat;
import org.apache.tomcat.util.descriptor.web.FilterDef;
import org.apache.tomcat.util.descriptor.web.FilterMap;
import org.apache.tomcat.util.http.Rfc6265CookieProcessor;
import com.resolvebid.config.AppConfig;
import com.resolvebid.security.AuthService;
import com.resolvebid.security.LoginAttemptService;
import com.resolvebid.service.MarketplaceService;
import jakarta.servlet.http.HttpServlet;

public final class EmbeddedWebServer implements AutoCloseable {
    private final MarketplaceService marketplace;
    private final AuthService auth;
    private final AppConfig config;
    private Tomcat tomcat;

    public EmbeddedWebServer(MarketplaceService marketplace, AuthService auth, AppConfig config) {
        this.marketplace = marketplace; this.auth = auth; this.config = config;
    }

    public void start() throws Exception {
        tomcat = new Tomcat();
        Path base = Files.createDirectories(Path.of("data", "tomcat"));
        tomcat.setBaseDir(base.toAbsolutePath().toString()); tomcat.setPort(config.port());
        var connector = tomcat.getConnector();
        connector.setProperty("address", config.production() ? "0.0.0.0" : "127.0.0.1");
        connector.setProperty("maxThreads", "80"); connector.setProperty("maxConnections", "1024");
        connector.setProperty("connectionTimeout", "15000"); connector.setMaxPostSize(32768);
        if (config.secureCookies()) { connector.setSecure(true); connector.setScheme("https"); }
        Context context = tomcat.addWebapp("", WebappResources.locate().toString());
        context.setUseHttpOnly(true); context.setSessionTimeout(30);
        Rfc6265CookieProcessor cookies = new Rfc6265CookieProcessor(); cookies.setSameSiteCookies("strict"); context.setCookieProcessor(cookies);

        LoginAttemptService attempts = new LoginAttemptService();
        servlet(context, "login", new LoginServlet(auth, attempts), "/login");
        servlet(context, "register", new RegisterServlet(auth), "/register");
        servlet(context, "logout", new LogoutServlet(), "/logout");
        SiteServlet site = new SiteServlet(marketplace);
        servlet(context, "site", site, "/home");
        for (String route : new String[]{"/explore", "/project", "/app/dashboard", "/app/new", "/app/access", "/how-it-works", "/about", "/contact", "/privacy"}) context.addServletMappingDecoded(route, "site");
        servlet(context, "actions", new ActionsServlet(marketplace, site), "/app/action/*");
        servlet(context, "health", new HealthServlet(marketplace), "/health");
        servlet(context, "requestApi", new RequestApiServlet(marketplace), "/api/requests");
        filter(context, "authAndHeaders", new AuthFilter(marketplace), "/*");
        for (int code : new int[]{400,403,404,405,413,500,503}) {
            var errorPage = new org.apache.tomcat.util.descriptor.web.ErrorPage();
            errorPage.setErrorCode(code); errorPage.setLocation("/WEB-INF/views/error.jsp"); context.addErrorPage(errorPage);
        }
        var reports = new org.apache.catalina.valves.ErrorReportValve(); reports.setShowReport(false); reports.setShowServerInfo(false); tomcat.getHost().getPipeline().addValve(reports);
        FilterDef hsts = new FilterDef(); hsts.setFilterName("hsts"); hsts.setFilter(new HttpHeaderSecurityFilter());
        hsts.addInitParameter("hstsEnabled", Boolean.toString(config.secureCookies())); context.addFilterDef(hsts);
        FilterMap hstsMap = new FilterMap(); hstsMap.setFilterName("hsts"); hstsMap.addURLPattern("/*"); context.addFilterMap(hstsMap);
        tomcat.start();
        if (!connector.getState().isAvailable() || !context.getState().isAvailable()) {
            close();
            throw new IllegalStateException("Dibsly could not start. Check PORT, database settings, and the server log.");
        }
    }

    private void servlet(Context context, String name, HttpServlet servlet, String mapping) {
        Tomcat.addServlet(context, name, servlet); context.addServletMappingDecoded(mapping, name);
    }
    private void filter(Context context, String name, jakarta.servlet.Filter filter, String mapping) {
        FilterDef def = new FilterDef(); def.setFilterName(name); def.setFilter(filter); context.addFilterDef(def);
        FilterMap map = new FilterMap(); map.setFilterName(name); map.addURLPattern(mapping); context.addFilterMap(map);
    }
    public void await() { if (tomcat != null) tomcat.getServer().await(); }
    @Override public void close() { if (tomcat != null) try { tomcat.stop(); tomcat.destroy(); } catch (Exception ignored) { } }
}
