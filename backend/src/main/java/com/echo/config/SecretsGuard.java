package com.echo.config;

import jakarta.annotation.PostConstruct;
import java.util.ArrayList;
import java.util.List;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Component;

/**
 * Refuses to start outside demo mode while any secret still holds a {@code change_me} placeholder from
 * .env.example or the application.yml defaults. In demo mode the placeholders are allowed but logged.
 */
@Component
public class SecretsGuard {

    private static final Logger log = LoggerFactory.getLogger(SecretsGuard.class);
    static final String PLACEHOLDER = "change_me";

    private final EchoProperties props;
    private final String databasePassword;

    public SecretsGuard(EchoProperties props, @Value("${spring.datasource.password:}") String databasePassword) {
        this.props = props;
        this.databasePassword = databasePassword;
    }

    @PostConstruct
    public void check() {
        List<String> defaults = placeholders(props.jwt().secret(), props.mlAdminToken(), databasePassword);
        if (defaults.isEmpty()) {
            return;
        }
        String which = String.join(", ", defaults);
        if (!props.demoMode()) {
            throw new IllegalStateException("Default placeholder secrets in use outside demo mode: " + which
                    + ". Set real values in .env (see .env.example).");
        }
        log.warn("Demo mode with placeholder secrets ({}). Never expose this deployment publicly.", which);
    }

    static List<String> placeholders(String jwtSecret, String mlAdminToken, String databasePassword) {
        List<String> found = new ArrayList<>();
        if (isPlaceholder(jwtSecret)) found.add("JWT_SECRET");
        if (isPlaceholder(mlAdminToken)) found.add("ML_ADMIN_TOKEN");
        if (isPlaceholder(databasePassword)) found.add("POSTGRES_PASSWORD");
        return found;
    }

    private static boolean isPlaceholder(String value) {
        return value != null && value.toLowerCase().contains(PLACEHOLDER);
    }
}
