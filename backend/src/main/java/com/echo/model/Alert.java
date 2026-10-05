package com.echo.model;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.FetchType;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.JoinColumn;
import jakarta.persistence.ManyToOne;
import jakarta.persistence.Table;
import java.time.OffsetDateTime;

@Entity
@Table(name = "alerts")
public class Alert {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(name = "user_id", nullable = false)
    private Long userId;

    @ManyToOne(fetch = FetchType.LAZY, optional = false)
    @JoinColumn(name = "company_id")
    private Company company;

    @Column(name = "report_id")
    private Long reportId;

    @Column(nullable = false)
    private String type;

    @Column(nullable = false)
    private String severity;

    @Column(nullable = false)
    private String message;

    @Column(name = "created_at", nullable = false)
    private OffsetDateTime createdAt = OffsetDateTime.now();

    @Column(name = "read_at")
    private OffsetDateTime readAt;

    protected Alert() {
    }

    public Alert(Long userId, Company company, Long reportId, String type, String severity, String message) {
        this.userId = userId;
        this.company = company;
        this.reportId = reportId;
        this.type = type;
        this.severity = severity;
        this.message = message.length() > 500 ? message.substring(0, 497) + "..." : message;
    }

    public Long getId() { return id; }
    public Long getUserId() { return userId; }
    public Company getCompany() { return company; }
    public Long getReportId() { return reportId; }
    public String getType() { return type; }
    public String getSeverity() { return severity; }
    public String getMessage() { return message; }
    public OffsetDateTime getCreatedAt() { return createdAt; }
    public OffsetDateTime getReadAt() { return readAt; }

    public void markRead() {
        if (readAt == null) readAt = OffsetDateTime.now();
    }
}
