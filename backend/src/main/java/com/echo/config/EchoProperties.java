package com.echo.config;

import java.util.List;
import org.springframework.boot.context.properties.ConfigurationProperties;

/** Typed {@code echo.*} configuration (see application.yml and .env.example). */
@ConfigurationProperties(prefix = "echo")
public record EchoProperties(
        String mlServiceUrl,
        boolean demoMode,
        String mlAdminToken,
        List<String> corsAllowedOrigins,
        Jwt jwt,
        Analysis analysis,
        Scheduler scheduler,
        Billing billing,
        RateLimit rateLimit) {

    public record Jwt(String secret, long expirationMinutes, String issuer) {
    }

    /** reportTtlHours: a report younger than this is served from the database instead of re-analysing. */
    public record Analysis(int reportTtlHours, int executorThreads, int mlTimeoutSeconds) {
    }

    public record Scheduler(boolean enabled, String watchlistRefreshCron, String monitoringCron, String retrainCron,
                            boolean autoRetrainOnDrift) {
    }

    /** mode=demo activates a plan immediately without payment; a payment provider plugs in at BillingService. */
    public record Billing(String mode) {
    }

    public record RateLimit(int anonymousAnalysesPerHour) {
    }
}
