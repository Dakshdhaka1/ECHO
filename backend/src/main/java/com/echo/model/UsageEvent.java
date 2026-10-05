package com.echo.model;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.Table;
import java.time.OffsetDateTime;

/** One metered action (analysis request, export, API call); drives plan limits and the usage panel. */
@Entity
@Table(name = "usage_events")
public class UsageEvent {

    public static final String ANALYSIS = "ANALYSIS";
    public static final String EXPORT = "EXPORT";
    public static final String API_CALL = "API_CALL";

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(name = "user_id")
    private Long userId;

    @Column(nullable = false)
    private String kind;

    @Column(name = "company_id")
    private Long companyId;

    @Column(name = "created_at", nullable = false)
    private OffsetDateTime createdAt = OffsetDateTime.now();

    protected UsageEvent() {
    }

    public UsageEvent(Long userId, String kind, Long companyId) {
        this.userId = userId;
        this.kind = kind;
        this.companyId = companyId;
    }

    public Long getId() { return id; }
    public String getKind() { return kind; }
    public OffsetDateTime getCreatedAt() { return createdAt; }
}
