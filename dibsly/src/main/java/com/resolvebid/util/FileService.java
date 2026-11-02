package com.resolvebid.util;

import java.io.BufferedWriter;
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.StandardOpenOption;
import java.time.LocalDateTime;
import java.util.List;
import com.resolvebid.model.Booking;

public final class FileService {
    private final Path dataDirectory;

    public FileService(Path dataDirectory) {
        this.dataDirectory = dataDirectory;
    }

    public synchronized void appendAudit(String event) {
        try {
            Files.createDirectories(dataDirectory);
            String line = LocalDateTime.now() + " | " + event + System.lineSeparator();
            Files.writeString(dataDirectory.resolve("audit.log"), line, StandardCharsets.UTF_8,
                    StandardOpenOption.CREATE, StandardOpenOption.APPEND);
        } catch (IOException ignored) {
            // Auditing must not interrupt a customer workflow.
        }
    }

    public Path exportBookings(List<Booking> bookings) throws IOException {
        Files.createDirectories(dataDirectory.resolve("exports"));
        Path target = dataDirectory.resolve("exports").resolve("bookings-" + System.currentTimeMillis() + ".csv");
        try (BufferedWriter writer = Files.newBufferedWriter(target, StandardCharsets.UTF_8)) {
            writer.write("booking_id,request_id,proposal_id,provider,category,scheduled_for,status");
            writer.newLine();
            for (Booking b : bookings) {
                writer.write(String.join(",", String.valueOf(b.id()), String.valueOf(b.requestId()),
                        String.valueOf(b.proposalId()), csv(b.providerName()), csv(b.category()),
                        b.scheduledFor().toString(), csv(b.status())));
                writer.newLine();
            }
        }
        appendAudit("Exported " + bookings.size() + " bookings to " + target.getFileName());
        return target;
    }

    private String csv(String value) { return "\"" + value.replace("\"", "\"\"") + "\""; }
}
