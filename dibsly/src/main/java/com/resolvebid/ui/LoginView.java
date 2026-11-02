package com.resolvebid.ui;

import java.util.function.Consumer;
import com.resolvebid.config.AppConfig;
import com.resolvebid.model.UserAccount;
import com.resolvebid.security.AuthService;
import javafx.geometry.Insets;
import javafx.geometry.Pos;
import javafx.scene.Parent;
import javafx.scene.control.Button;
import javafx.scene.control.Label;
import javafx.scene.control.PasswordField;
import javafx.scene.control.TextField;
import javafx.scene.layout.BorderPane;
import javafx.scene.layout.Priority;
import javafx.scene.layout.Region;
import javafx.scene.layout.VBox;

public final class LoginView {
    private final BorderPane root = new BorderPane();
    public LoginView(AuthService auth, AppConfig config, Consumer<UserAccount> onSuccess) {
        VBox story = new VBox(18); story.setPadding(new Insets(64)); story.setPrefWidth(620);
        story.setStyle("-fx-background-color:#13213C;");
        Label brand = label("Dibsly", 24, "white", true);
        Region space = new Region(); VBox.setVgrow(space, Priority.ALWAYS);
        Label eyebrow = label("SERVICE MARKETPLACE", 12, "#8FB2FF", true);
        Label title = label("Turn a problem\ninto the right solution.", 46, "white", true);
        Label copy = label("Describe the issue. Compare clear proposals. Book with confidence.", 16, "#BAC7DE", false);
        copy.setWrapText(true); copy.setMaxWidth(470);
        Label tech = label("Java 21  ·  JavaFX  ·  JDBC  ·  Secure sessions", 12, "#8193B4", false);
        story.getChildren().addAll(brand, space, eyebrow, title, copy, tech);

        VBox panel = new VBox(14); panel.setAlignment(Pos.CENTER_LEFT); panel.setPadding(new Insets(72));
        panel.setStyle("-fx-background-color:white;");
        Label welcome = label("Welcome back", 13, "#2563EB", true);
        Label heading = label("Sign in", 32, "#172033", true);
        Label intro = label("Access your private ResolveBid workspace.", 14, "#667085", false);
        TextField username = new TextField(); username.setPromptText("Username"); username.setMaxWidth(380);
        PasswordField password = new PasswordField(); password.setPromptText("Password"); password.setMaxWidth(380);
        Label feedback = label("", 12, "#B42318", true); feedback.setWrapText(true);
        Button signIn = new Button("Sign in securely"); signIn.setDefaultButton(true);
        signIn.setStyle("-fx-background-color:#2563EB;-fx-text-fill:white;-fx-font-weight:800;-fx-background-radius:8;-fx-padding:12 22;");
        Runnable submit = () -> auth.authenticate(username.getText(), password.getText().toCharArray())
                .ifPresentOrElse(onSuccess, () -> feedback.setText("Username or password is incorrect."));
        signIn.setOnAction(e -> submit.run()); password.setOnAction(e -> submit.run());
        panel.getChildren().addAll(welcome, heading, intro, username, password, signIn, feedback);
        if (!config.production()) panel.getChildren().add(label("Development admin: " + config.adminUsername() + " / ChangeMe123!", 11, "#8791A5", false));
        root.setLeft(story); root.setCenter(panel);
    }
    public Parent root() { return root; }
    private Label label(String text, int size, String color, boolean bold) {
        Label label = new Label(text); label.setStyle("-fx-font-size:"+size+"px;-fx-text-fill:"+color+";"+(bold?"-fx-font-weight:800;":"")); return label;
    }
}
