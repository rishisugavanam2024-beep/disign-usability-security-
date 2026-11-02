package com.resolvebid.ui;

import java.math.BigDecimal;
import java.nio.file.Path;
import java.text.NumberFormat;
import java.time.LocalDate;
import java.time.format.DateTimeFormatter;
import java.util.List;
import java.util.Map;
import java.util.function.Function;
import com.resolvebid.exception.ValidationException;
import com.resolvebid.model.Booking;
import com.resolvebid.model.DashboardStats;
import com.resolvebid.model.Proposal;
import com.resolvebid.model.ServiceRequest;
import com.resolvebid.model.Permission;
import com.resolvebid.model.Role;
import com.resolvebid.model.UserAccount;
import com.resolvebid.service.MarketplaceService;
import com.resolvebid.util.AsyncTaskService;
import javafx.application.Platform;
import javafx.beans.property.ReadOnlyObjectWrapper;
import javafx.collections.FXCollections;
import javafx.collections.ObservableList;
import javafx.geometry.Insets;
import javafx.geometry.Pos;
import javafx.scene.Node;
import javafx.scene.control.Alert;
import javafx.scene.control.Button;
import javafx.scene.control.ComboBox;
import javafx.scene.control.DatePicker;
import javafx.scene.control.Label;
import javafx.scene.control.ListCell;
import javafx.scene.control.ListView;
import javafx.scene.control.ScrollPane;
import javafx.scene.control.SelectionMode;
import javafx.scene.control.Separator;
import javafx.scene.control.TableCell;
import javafx.scene.control.TableColumn;
import javafx.scene.control.TableView;
import javafx.scene.control.TextArea;
import javafx.scene.control.TextField;
import javafx.scene.layout.BorderPane;
import javafx.scene.layout.FlowPane;
import javafx.scene.layout.HBox;
import javafx.scene.layout.Priority;
import javafx.scene.layout.Region;
import javafx.scene.layout.StackPane;
import javafx.scene.layout.VBox;

public final class AppShell {
    private static final String NAVY = "#14213D";
    private static final String BLUE = "#246BFD";
    private static final String BG = "#F5F7FB";
    private static final String TEXT = "#172033";
    private static final NumberFormat MONEY = NumberFormat.getCurrencyInstance(new java.util.Locale("en", "IN"));
    private static final DateTimeFormatter DATE = DateTimeFormatter.ofPattern("dd MMM yyyy");

    private final MarketplaceService service;
    private final AsyncTaskService async;
    private final UserAccount user;
    private final Runnable logout;
    private final BorderPane root = new BorderPane();
    private final StackPane content = new StackPane();
    private final ObservableList<ServiceRequest> requests = FXCollections.observableArrayList();
    private final ObservableList<Booking> bookings = FXCollections.observableArrayList();
    private final Label openMetric = metricValue("–");
    private final Label proposalMetric = metricValue("–");
    private final Label bookingMetric = metricValue("–");
    private final Label completeMetric = metricValue("–");
    private final Label serverStatus = new Label("Local service: starting…");
    private final ListView<ServiceRequest> recentRequests = requestList();
    private final ListView<ServiceRequest> providerRequests = requestList();
    private final ComboBox<ServiceRequest> compareRequest = new ComboBox<>();
    private final TableView<Proposal> proposalTable = new TableView<>();
    private final TableView<Booking> bookingTable = new TableView<>();
    private Map<Long, Double> proposalScores = Map.of();

    public AppShell(MarketplaceService service, AsyncTaskService async, UserAccount user, Runnable logout) {
        this.service = service;
        this.async = async;
        this.user = user;
        this.logout = logout;
        root.setStyle("-fx-background-color:" + BG + ";-fx-font-family:'Segoe UI';-fx-text-fill:" + TEXT + ";");
        root.setLeft(sidebar());
        root.setTop(topbar());
        root.setCenter(content);
        showPage(dashboardPage());
        refreshAll();
    }

    public BorderPane root() { return root; }

    public void setServerStatus(String message, boolean online) {
        Platform.runLater(() -> {
            serverStatus.setText(message);
            serverStatus.setStyle("-fx-text-fill:" + (online ? "#12805C" : "#B5473C") + ";-fx-font-size:12px;");
        });
    }

    private Node sidebar() {
        VBox box = new VBox(8);
        box.setPadding(new Insets(26, 18, 24, 18));
        box.setPrefWidth(235);
        box.setStyle("-fx-background-color:" + NAVY + ";");

        Label logo = new Label("Dibsly");
        logo.setStyle("-fx-text-fill:white;-fx-font-size:26px;-fx-font-weight:800;");
        Label tag = new Label("Problems meet solutions");
        tag.setStyle("-fx-text-fill:#AEBBDD;-fx-font-size:12px;");
        VBox.setMargin(tag, new Insets(0, 0, 26, 0));

        Button dashboard = navButton("Overview");
        Button post = navButton("Post a problem");
        Button provider = navButton("Provider desk");
        Button compare = navButton("Compare & book");
        Button records = navButton("Records & exports");
        dashboard.setOnAction(e -> showPage(dashboardPage()));
        post.setOnAction(e -> showPage(postProblemPage()));
        provider.setOnAction(e -> { providerRequests.setItems(requests.filtered(r -> r.status().name().equals("OPEN"))); showPage(providerPage()); });
        compare.setOnAction(e -> { compareRequest.setItems(requests.filtered(r -> r.status().name().equals("OPEN"))); showPage(comparePage()); });
        records.setOnAction(e -> showPage(recordsPage()));

        Region spacer = new Region();
        VBox.setVgrow(spacer, Priority.ALWAYS);
        Label footer = new Label("Java 21 · JavaFX · JDBC\nServlet + JSP service");
        footer.setStyle("-fx-text-fill:#8594B8;-fx-font-size:11px;-fx-line-spacing:3px;");
        box.getChildren().addAll(logo, tag, dashboard);
        if (user.can(Permission.POST_REQUEST)) box.getChildren().add(post);
        if (user.can(Permission.SUBMIT_PROPOSAL)) box.getChildren().add(provider);
        if (user.can(Permission.ACCEPT_PROPOSAL)) box.getChildren().add(compare);
        if (user.role() == Role.ADMIN) box.getChildren().add(records);
        box.getChildren().addAll(spacer, new Separator(), footer);
        return box;
    }

    private Node topbar() {
        HBox bar = new HBox(16);
        bar.setAlignment(Pos.CENTER_LEFT);
        bar.setPadding(new Insets(14, 26, 14, 26));
        bar.setStyle("-fx-background-color:white;-fx-border-color:#E7EAF0;-fx-border-width:0 0 1 0;");
        Label workspace = new Label("Service marketplace workspace");
        workspace.setStyle("-fx-font-size:14px;-fx-font-weight:700;-fx-text-fill:" + TEXT + ";");
        Region spacer = new Region();
        HBox.setHgrow(spacer, Priority.ALWAYS);
        serverStatus.setStyle("-fx-text-fill:#A06A00;-fx-font-size:12px;");
        Button refresh = secondaryButton("Refresh data");
        refresh.setOnAction(e -> refreshAll());
        Label identity = new Label(user.displayName() + " · " + user.role());
        identity.setStyle("-fx-text-fill:#4E5B73;-fx-font-size:12px;-fx-font-weight:700;");
        Button signOut = secondaryButton("Sign out"); signOut.setOnAction(e -> logout.run());
        bar.getChildren().addAll(workspace, spacer, serverStatus, identity, refresh, signOut);
        return bar;
    }

    private Node dashboardPage() {
        VBox page = page("Overview", "From problem description to a confirmed service in one transparent flow.");
        FlowPane metrics = new FlowPane(14, 14);
        metrics.getChildren().addAll(metricCard("Open requests", openMetric, "Waiting for proposals"), metricCard("Proposals", proposalMetric, "Provider responses"), metricCard("Bookings", bookingMetric, "Confirmed services"), metricCard("Completed", completeMetric, "Closed requests"));

        HBox body = new HBox(18);
        VBox latest = card();
        Label latestTitle = sectionTitle("Latest customer problems");
        latest.getChildren().addAll(latestTitle, recentRequests);
        VBox.setVgrow(recentRequests, Priority.ALWAYS);
        HBox.setHgrow(latest, Priority.ALWAYS);

        VBox journey = card();
        journey.setPrefWidth(330);
        journey.getChildren().addAll(sectionTitle("How Dibsly works"), step("1", "Describe the problem", "No technical diagnosis required."), step("2", "Receive proposals", "Providers share price, ETA and warranty."), step("3", "Compare value", "A score helps surface balanced offers."), step("4", "Book with confidence", "The accepted proposal becomes a record."));
        body.getChildren().addAll(latest, journey);
        VBox.setVgrow(body, Priority.ALWAYS);
        page.getChildren().addAll(metrics, body);
        return scroll(page);
    }

    private Node postProblemPage() {
        VBox page = page("Post a problem", "Tell providers what is wrong. Dibsly structures the request for you.");
        VBox form = card();
        form.setMaxWidth(820);
        ComboBox<String> category = new ComboBox<>(FXCollections.observableArrayList(MarketplaceService.CATEGORIES));
        category.setPromptText("Choose a category"); category.setMaxWidth(Double.MAX_VALUE);
        TextArea description = area("Describe symptoms, when they started, and anything already tried.", 5);
        ComboBox<String> urgency = new ComboBox<>(FXCollections.observableArrayList("Within 24 hours", "This week", "Flexible"));
        urgency.setPromptText("Choose urgency"); urgency.setMaxWidth(Double.MAX_VALUE);
        TextField budget = field("Budget in INR");
        Button submit = primaryButton("Publish request");
        Label feedback = feedbackLabel();
        submit.setOnAction(e -> {
            try {
                long id = service.postRequest(user, category.getValue(), description.getText(), urgency.getValue(), budget.getText());
                feedback.setText("Request #" + id + " published. Providers can now respond."); feedback.setStyle(successStyle());
                description.clear(); budget.clear(); category.setValue(null); urgency.setValue(null); refreshAll();
            } catch (ValidationException ex) { showValidation(feedback, ex); }
            catch (RuntimeException ex) { showError(ex); }
        });
        form.getChildren().addAll(labelled("Customer", new Label(user.displayName())), labelled("Category", category), labelled("Problem description", description), row(labelled("Urgency", urgency), labelled("Maximum budget", budget)), submit, feedback);
        page.getChildren().add(form);
        return scroll(page);
    }

    private Node providerPage() {
        VBox page = page("Provider desk", "Review open problems and respond with a clear, comparable proposal.");
        HBox columns = new HBox(18);
        VBox requestCard = card();
        requestCard.setPrefWidth(470);
        requestCard.getChildren().addAll(sectionTitle("Open requests"), providerRequests);
        VBox.setVgrow(providerRequests, Priority.ALWAYS);

        VBox form = card();
        TextArea diagnosis = area("Your diagnosis and the work included", 4);
        TextField price = field("Quoted price in INR");
        TextField eta = field("ETA in days");
        TextField warranty = field("Warranty in days");
        Label feedback = feedbackLabel();
        Button send = primaryButton("Submit proposal");
        send.setOnAction(e -> {
            try {
                service.submitProposal(user, providerRequests.getSelectionModel().getSelectedItem(), diagnosis.getText(), price.getText(), eta.getText(), warranty.getText());
                feedback.setText("Proposal submitted successfully."); feedback.setStyle(successStyle());
                diagnosis.clear(); price.clear(); eta.clear(); warranty.clear(); refreshAll();
            } catch (ValidationException ex) { showValidation(feedback, ex); }
            catch (RuntimeException ex) { showError(ex); }
        });
        form.getChildren().addAll(sectionTitle("Create proposal"), labelled("Provider", new Label(user.displayName())), labelled("Diagnosis and scope", diagnosis), row(labelled("Price", price), labelled("ETA", eta)), labelled("Warranty", warranty), send, feedback);
        HBox.setHgrow(form, Priority.ALWAYS);
        columns.getChildren().addAll(requestCard, form);
        page.getChildren().add(columns);
        VBox.setVgrow(columns, Priority.ALWAYS);
        return scroll(page);
    }

    private Node comparePage() {
        VBox page = page("Compare & book", "Use the value score as a guide, then choose the proposal that fits your needs.");
        VBox box = card();
        compareRequest.setPromptText("Select an open request"); compareRequest.setMaxWidth(Double.MAX_VALUE);
        configureProposalTable();
        DatePicker date = new DatePicker(LocalDate.now().plusDays(1));
        Label note = new Label(service.rankingExplanation()); note.setStyle("-fx-text-fill:#67728A;-fx-font-size:12px;");
        Label feedback = feedbackLabel();
        Button book = primaryButton("Accept selected proposal");
        compareRequest.setOnAction(e -> loadProposals(compareRequest.getValue()));
        book.setOnAction(e -> {
            try {
                service.acceptProposal(user, compareRequest.getValue(), proposalTable.getSelectionModel().getSelectedItem(), date.getValue());
                feedback.setText("Booking confirmed for " + DATE.format(date.getValue()) + "."); feedback.setStyle(successStyle()); refreshAll();
            } catch (ValidationException ex) { showValidation(feedback, ex); }
            catch (RuntimeException ex) { showError(ex); }
        });
        box.getChildren().addAll(labelled("Customer request", compareRequest), proposalTable, note, row(labelled("Service date", date), book), feedback);
        VBox.setVgrow(proposalTable, Priority.ALWAYS);
        page.getChildren().add(box);
        VBox.setVgrow(box, Priority.ALWAYS);
        return scroll(page);
    }

    private Node recordsPage() {
        VBox page = page("Records & exports", "Confirmed bookings stay available for review and can be exported to CSV.");
        VBox box = card();
        configureBookingTable();
        Label feedback = feedbackLabel();
        Button export = primaryButton("Export booking CSV");
        export.setOnAction(e -> {
            export.setDisable(true); feedback.setText("Preparing export…");
            async.submit(() -> service.exportBookings(user), path -> { export.setDisable(false); feedback.setText("Saved to " + path.toAbsolutePath()); feedback.setStyle(successStyle()); }, error -> { export.setDisable(false); feedback.setText("Export failed: " + error.getMessage()); feedback.setStyle(errorStyle()); });
        });
        box.getChildren().addAll(bookingTable, export, feedback);
        VBox.setVgrow(bookingTable, Priority.ALWAYS);
        page.getChildren().add(box);
        VBox.setVgrow(box, Priority.ALWAYS);
        return scroll(page);
    }

    private void refreshAll() {
        async.submit(() -> new Snapshot(service.requestsFor(user), service.bookings(user), service.stats(user)), snapshot -> {
            requests.setAll(snapshot.requests()); bookings.setAll(snapshot.bookings());
            recentRequests.setItems(requests); providerRequests.setItems(requests.filtered(r -> r.status().name().equals("OPEN")));
            compareRequest.setItems(requests.filtered(r -> r.status().name().equals("OPEN"))); bookingTable.setItems(bookings);
            updateMetrics(snapshot.stats());
        }, this::showError);
    }

    private void loadProposals(ServiceRequest request) {
        if (request == null) { proposalTable.getItems().clear(); return; }
        async.submit(() -> service.rankedProposals(user, request.id()), proposals -> {
            proposalScores = service.scores(proposals); proposalTable.setItems(FXCollections.observableArrayList(proposals));
            if (!proposals.isEmpty()) proposalTable.getSelectionModel().selectFirst();
        }, this::showError);
    }

    private void updateMetrics(DashboardStats stats) {
        openMetric.setText(String.valueOf(stats.openRequests())); proposalMetric.setText(String.valueOf(stats.proposals())); bookingMetric.setText(String.valueOf(stats.bookings())); completeMetric.setText(String.valueOf(stats.completed()));
    }

    @SuppressWarnings("unchecked") private void configureProposalTable() {
        if (!proposalTable.getColumns().isEmpty()) return;
        proposalTable.setColumnResizePolicy(TableView.CONSTRAINED_RESIZE_POLICY_FLEX_LAST_COLUMN);
        proposalTable.getSelectionModel().setSelectionMode(SelectionMode.SINGLE);
        proposalTable.setPrefHeight(360);
        proposalTable.getColumns().addAll(column("Provider", Proposal::providerName), column("Diagnosis", Proposal::diagnosis), moneyColumn("Price", Proposal::price), column("ETA", p -> p.etaDays() + " days"), column("Warranty", p -> p.warrantyDays() + " days"), column("Value score", p -> proposalScores.getOrDefault(p.id(), 0.0)));
    }

    @SuppressWarnings("unchecked") private void configureBookingTable() {
        if (!bookingTable.getColumns().isEmpty()) return;
        bookingTable.setColumnResizePolicy(TableView.CONSTRAINED_RESIZE_POLICY_FLEX_LAST_COLUMN);
        bookingTable.setItems(bookings);
        bookingTable.getColumns().addAll(column("Booking", b -> "#" + b.id()), column("Request", b -> "#" + b.requestId()), column("Category", Booking::category), column("Provider", Booking::providerName), column("Scheduled", b -> DATE.format(b.scheduledFor())), column("Status", Booking::status));
    }

    private <T,R> TableColumn<T,R> column(String title, Function<T,R> value) {
        TableColumn<T,R> col = new TableColumn<>(title); col.setCellValueFactory(data -> new ReadOnlyObjectWrapper<>(value.apply(data.getValue()))); return col;
    }

    private <T> TableColumn<T,BigDecimal> moneyColumn(String title, Function<T,BigDecimal> value) {
        TableColumn<T,BigDecimal> col = column(title, value); col.setCellFactory(c -> new TableCell<>() { @Override protected void updateItem(BigDecimal item, boolean empty) { super.updateItem(item, empty); setText(empty || item == null ? null : MONEY.format(item)); } }); return col;
    }

    private VBox page(String title, String subtitle) {
        VBox box = new VBox(18); box.setPadding(new Insets(28)); box.setFillWidth(true);
        Label h1 = new Label(title); h1.setStyle("-fx-font-size:28px;-fx-font-weight:800;-fx-text-fill:" + TEXT + ";");
        Label sub = new Label(subtitle); sub.setWrapText(true); sub.setStyle("-fx-font-size:14px;-fx-text-fill:#67728A;");
        box.getChildren().addAll(h1, sub); return box;
    }

    private VBox card() { VBox box = new VBox(14); box.setPadding(new Insets(20)); box.setStyle("-fx-background-color:white;-fx-background-radius:12;-fx-border-color:#E7EAF0;-fx-border-radius:12;"); return box; }
    private Node metricCard(String name, Label value, String caption) { VBox box = card(); box.setPrefWidth(218); Label n = new Label(name); n.setStyle("-fx-font-size:12px;-fx-text-fill:#67728A;-fx-font-weight:700;"); Label c = new Label(caption); c.setStyle("-fx-font-size:11px;-fx-text-fill:#98A2B5;"); box.getChildren().addAll(n,value,c); return box; }
    private static Label metricValue(String text) { Label l = new Label(text); l.setStyle("-fx-font-size:30px;-fx-font-weight:800;-fx-text-fill:" + BLUE + ";"); return l; }
    private Label sectionTitle(String text) { Label l = new Label(text); l.setStyle("-fx-font-size:16px;-fx-font-weight:800;-fx-text-fill:" + TEXT + ";"); return l; }
    private Node step(String number, String title, String copy) { Label badge = new Label(number); badge.setAlignment(Pos.CENTER); badge.setMinSize(30,30); badge.setStyle("-fx-background-color:#E8F0FF;-fx-background-radius:15;-fx-text-fill:"+BLUE+";-fx-font-weight:800;"); Label t = new Label(title+"\n"+copy); t.setWrapText(true); t.setStyle("-fx-text-fill:"+TEXT+";-fx-font-size:12px;"); HBox h = new HBox(12,badge,t); h.setAlignment(Pos.TOP_LEFT); return h; }
    private Button navButton(String text) { Button b = new Button(text); b.setMaxWidth(Double.MAX_VALUE); b.setAlignment(Pos.CENTER_LEFT); b.setPadding(new Insets(11,14,11,14)); b.setStyle("-fx-background-color:transparent;-fx-text-fill:#D8E0F3;-fx-font-size:13px;-fx-cursor:hand;"); return b; }
    private Button primaryButton(String text) { Button b = new Button(text); b.setPadding(new Insets(11,18,11,18)); b.setStyle("-fx-background-color:"+BLUE+";-fx-text-fill:white;-fx-font-weight:800;-fx-background-radius:8;-fx-cursor:hand;"); return b; }
    private Button secondaryButton(String text) { Button b = new Button(text); b.setStyle("-fx-background-color:#EFF3FA;-fx-text-fill:"+NAVY+";-fx-font-weight:700;-fx-background-radius:7;"); return b; }
    private TextField field(String prompt) { TextField f = new TextField(); f.setPromptText(prompt); f.setMaxWidth(Double.MAX_VALUE); return f; }
    private TextArea area(String prompt, int rows) { TextArea a = new TextArea(); a.setPromptText(prompt); a.setPrefRowCount(rows); a.setWrapText(true); return a; }
    private VBox labelled(String title, Node node) { Label l = new Label(title); l.setStyle("-fx-font-size:12px;-fx-font-weight:700;-fx-text-fill:#4E5B73;"); VBox box = new VBox(6,l,node); HBox.setHgrow(box, Priority.ALWAYS); return box; }
    private HBox row(Node... nodes) { HBox h = new HBox(14,nodes); h.setAlignment(Pos.BOTTOM_LEFT); for(Node n:nodes) HBox.setHgrow(n, Priority.ALWAYS); return h; }
    private ListView<ServiceRequest> requestList() { ListView<ServiceRequest> list = new ListView<>(); list.setPlaceholder(new Label("No requests yet")); list.setCellFactory(v -> new ListCell<>() { @Override protected void updateItem(ServiceRequest r, boolean empty) { super.updateItem(r,empty); if(empty||r==null){setText(null);setGraphic(null);}else{Label title=new Label(r.category()+" · "+r.urgency());title.setStyle("-fx-font-weight:800;-fx-text-fill:"+TEXT+";");Label desc=new Label(r.description());desc.setWrapText(true);desc.setStyle("-fx-text-fill:#5F6B82;-fx-font-size:12px;");Label meta=new Label(MONEY.format(r.budget())+" budget · "+r.status());meta.setStyle("-fx-text-fill:"+BLUE+";-fx-font-size:11px;");VBox box=new VBox(4,title,desc,meta);box.setPadding(new Insets(8));setGraphic(box);setText(null);}}}); return list; }
    private ScrollPane scroll(Node node) { ScrollPane pane = new ScrollPane(node); pane.setFitToWidth(true); pane.setFitToHeight(true); pane.setStyle("-fx-background:"+BG+";-fx-background-color:"+BG+";"); return pane; }
    private Label feedbackLabel() { Label l = new Label(); l.setWrapText(true); return l; }
    private String successStyle() { return "-fx-text-fill:#12805C;-fx-font-weight:700;"; }
    private String errorStyle() { return "-fx-text-fill:#B5473C;-fx-font-weight:700;"; }
    private void showValidation(Label label, ValidationException ex) { label.setText(ex.getMessage()); label.setStyle(errorStyle()); }
    private void showError(Throwable error) { Alert alert = new Alert(Alert.AlertType.ERROR); alert.setTitle("Dibsly"); alert.setHeaderText("Something went wrong"); alert.setContentText(error.getMessage()); alert.showAndWait(); }
    private void showPage(Node page) { content.getChildren().setAll(page); }

    private record Snapshot(List<ServiceRequest> requests, List<Booking> bookings, DashboardStats stats) { }
}
