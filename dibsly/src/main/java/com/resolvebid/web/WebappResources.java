package com.resolvebid.web;

import java.io.IOException;
import java.io.InputStream;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.StandardCopyOption;
import java.util.List;

final class WebappResources {
    private static final List<String> FILES = List.of("index.jsp", "assets/app.css", "assets/app.js", "assets/brand.svg", "assets/manrope.ttf", "assets/FONT-LICENSE.txt",
            "WEB-INF/views/login.jsp", "WEB-INF/views/register.jsp", "WEB-INF/views/site.jsp", "WEB-INF/views/error.jsp",
            "WEB-INF/views/header.jspf", "WEB-INF/views/footer.jspf", "WEB-INF/views/info.jsp");
    private WebappResources() { }
    static Path locate() throws IOException {
        Path source = Path.of("src", "main", "webapp").toAbsolutePath();
        if (Files.isDirectory(source)) return source;
        Path target = Files.createDirectories(Path.of("data", "runtime-webapp").toAbsolutePath());
        for (String file : FILES) {
            Path output = target.resolve(file); Files.createDirectories(output.getParent());
            try (InputStream input = WebappResources.class.getResourceAsStream("/webapp/" + file)) {
                if (input == null) throw new IOException("Missing packaged web resource: " + file);
                Files.copy(input, output, StandardCopyOption.REPLACE_EXISTING);
            }
        }
        return target;
    }
}
