package com.resolvebid.util;

import java.util.concurrent.Callable;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.function.Consumer;
import javafx.application.Platform;

public final class AsyncTaskService implements AutoCloseable {
    private final ExecutorService pool = Executors.newFixedThreadPool(3, r -> {
        Thread thread = new Thread(r, "resolvebid-worker");
        thread.setDaemon(true);
        return thread;
    });

    public <T> void submit(Callable<T> work, Consumer<T> success, Consumer<Throwable> failure) {
        pool.submit(() -> {
            try {
                T result = work.call();
                Platform.runLater(() -> success.accept(result));
            } catch (Throwable error) {
                Platform.runLater(() -> failure.accept(error));
            }
        });
    }

    @Override public void close() { pool.shutdownNow(); }
}
