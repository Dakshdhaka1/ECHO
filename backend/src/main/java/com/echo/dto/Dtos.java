package com.echo.dto;

import com.echo.model.Alert;
import com.echo.model.AnalysisJob;
import com.echo.model.ApiKey;
import com.echo.model.Company;
import com.echo.model.Plan;
import com.echo.model.User;
import jakarta.validation.constraints.Email;
import jakarta.validation.constraints.Max;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.Size;
import java.math.BigDecimal;
import java.time.Instant;
import java.time.LocalDate;
import java.time.OffsetDateTime;
import java.util.List;
import java.util.UUID;
import tools.jackson.databind.JsonNode;

/** Request/response records of the public REST API (documented in OpenAPI at /api/swagger-ui). */
public final class Dtos {

    private Dtos() {
    }

    // ------------------------------------------------------------------ auth & users
    public record RegisterRequest(
            @NotBlank @Email @Size(max = 255) String email,
            @NotBlank @Size(min = 8, max = 100) String password,
            @Size(max = 100) String displayName) {
    }

    public record LoginRequest(@NotBlank @Email String email, @NotBlank String password) {
    }

    public record UserDto(Long id, String email, String displayName, String role, String plan,
                          OffsetDateTime createdAt) {
        public static UserDto of(User u) {
            return new UserDto(u.getId(), u.getEmail(), u.getDisplayName(), u.getRole().name(), u.getPlan().name(),
                    u.getCreatedAt());
        }
    }

    public record AuthResponse(String token, Instant expiresAt, UserDto user) {
    }

    public record PlanDto(String name, String label, int monthlyPriceUsd, int maxWatchlists, int maxWatchlistItems,
                          int maxCompare, int historyDays, int analysesPerDay, boolean pdfExport, int maxApiKeys,
                          int apiCallsPerDay) {
        public static PlanDto of(Plan p) {
            return new PlanDto(p.name(), p.label(), p.monthlyPriceUsd(), p.maxWatchlists(), p.maxWatchlistItems(),
                    p.maxCompare(), p.historyDays(), p.analysesPerDay(), p.pdfExport(), p.maxApiKeys(),
                    p.apiCallsPerDay());
        }
    }

    public record UsageDto(long analysesToday, long apiCallsToday, long exportsToday) {
    }

    public record MeDto(UserDto user, PlanDto plan, UsageDto usage, long unreadAlerts) {
    }

    public record CheckoutRequest(@NotBlank String plan) {
    }

    public record CheckoutResponse(UserDto user, String mode, String message) {
    }

    // ------------------------------------------------------------------ companies & reports
    public record CompanyDto(Long id, String market, String marketId, String name, String ticker, String exchange,
                             String sector, String sic, boolean demo) {
        public static CompanyDto of(Company c) {
            return new CompanyDto(c.getId(), c.getMarket(), c.getMarketId(), c.getName(), c.getTicker(),
                    c.getExchange(), c.getSector(), c.getIndustryCode(), c.isDemo());
        }
    }

    public record SearchResultDto(CompanyDto company, double matchScore, List<String> formerNames) {
    }

    public record JobDto(UUID id, Long companyId, LocalDate asOf, String status, String error,
                         OffsetDateTime createdAt, OffsetDateTime startedAt, OffsetDateTime finishedAt, Long reportId) {
        public static JobDto of(AnalysisJob j, Long reportId) {
            return new JobDto(j.getId(), j.getCompany().getId(), j.getAsOf(), j.getStatus().name(), j.getError(),
                    j.getCreatedAt(), j.getStartedAt(), j.getFinishedAt(), reportId);
        }
    }

    public record ReportDto(Long id, CompanyDto company, LocalDate asOf, OffsetDateTime generatedAt, boolean caseStudy,
                            Short healthScore, String band, BigDecimal confidence, BigDecimal distressProbability,
                            String modelVersion, String explanationGenerator, boolean stale, JsonNode payload) {
    }

    /** GET /report answers 200 with a report, or 202 with the job that is producing one (optionally a stale report). */
    public record ReportEnvelope(String status, ReportDto report, JobDto job) {
    }

    public record AnalyzeRequest(LocalDate asOf) {
    }

    public record HistoryPointDto(LocalDate asOf, Short healthScore, BigDecimal confidence, String source,
                                  JsonNode pillars) {
    }

    public record CompareItemDto(CompanyDto company, Long reportId, LocalDate asOf, Short healthScore, String band,
                                 BigDecimal confidence, BigDecimal distressProbability, JsonNode pillars,
                                 JsonNode segment, int signals) {
    }

    /** One analysed (company, as-of) point of the demo universe for the signals radar. */
    public record RadarPointDto(Long companyId, String ticker, String name, String role, boolean caseStudy,
                                LocalDate asOf, Long reportId, Short healthScore, String band, BigDecimal confidence,
                                BigDecimal distressProbability, Double distressBaseRate, String distressUnavailableReason,
                                Double financialScore, int signals) {
    }

    /** Radar points plus the (company, as-of) pairs of the demo universe that have no report yet. */
    public record RadarDto(List<RadarPointDto> points, List<RadarPendingDto> pending) {
    }

    public record RadarPendingDto(Long companyId, String ticker, String asOf) {
    }

    // ------------------------------------------------------------------ watchlists & alerts
    public record CreateWatchlistRequest(@NotBlank @Size(max = 100) String name) {
    }

    public record AddWatchlistItemRequest(Long companyId, @Min(1) @Max(100) Integer scoreDropThreshold) {
    }

    public record WatchlistItemDto(CompanyDto company, short scoreDropThreshold, OffsetDateTime addedAt,
                                   Short latestScore, String band, LocalDate asOf) {
    }

    public record WatchlistDto(Long id, String name, OffsetDateTime createdAt, List<WatchlistItemDto> items) {
    }

    public record AlertDto(Long id, CompanyDto company, Long reportId, String type, String severity, String message,
                           OffsetDateTime createdAt, boolean read) {
        public static AlertDto of(Alert a) {
            return new AlertDto(a.getId(), CompanyDto.of(a.getCompany()), a.getReportId(), a.getType(),
                    a.getSeverity(), a.getMessage(), a.getCreatedAt(), a.getReadAt() != null);
        }
    }

    // ------------------------------------------------------------------ API keys
    public record CreateApiKeyRequest(@NotBlank @Size(max = 100) String name) {
    }

    public record ApiKeyDto(Long id, String name, String prefix, OffsetDateTime createdAt, OffsetDateTime lastUsedAt,
                            boolean active) {
        public static ApiKeyDto of(ApiKey k) {
            return new ApiKeyDto(k.getId(), k.getName(), k.getKeyPrefix(), k.getCreatedAt(), k.getLastUsedAt(),
                    k.isActive());
        }
    }

    public record CreatedApiKeyDto(ApiKeyDto key, String secret) {
    }

    // ------------------------------------------------------------------ admin
    public record AdminUserUpdate(String plan, String role) {
    }

    public record RetrainRequest(@NotBlank String model, Boolean promote) {
    }

    public record StatsDto(long companies, long reports, long users, long jobsDone, JsonNode models) {
    }
}
