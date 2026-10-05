package com.echo.model;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.EnumType;
import jakarta.persistence.Enumerated;
import jakarta.persistence.FetchType;
import jakarta.persistence.Id;
import jakarta.persistence.JoinColumn;
import jakarta.persistence.ManyToOne;
import jakarta.persistence.Table;
import java.time.LocalDate;
import java.time.OffsetDateTime;
import java.util.UUID;

@Entity
@Table(name = "analysis_jobs")
public class AnalysisJob {

    public enum Status { QUEUED, RUNNING, DONE, FAILED }

    @Id
    private UUID id = UUID.randomUUID();

    @ManyToOne(fetch = FetchType.LAZY, optional = false)
    @JoinColumn(name = "company_id")
    private Company company;

    @Column(name = "as_of", nullable = false)
    private LocalDate asOf;

    @Enumerated(EnumType.STRING)
    @Column(nullable = false)
    private Status status = Status.QUEUED;

    @Column(name = "requested_by")
    private Long requestedBy;

    private String error;

    @Column(name = "created_at", nullable = false)
    private OffsetDateTime createdAt = OffsetDateTime.now();

    @Column(name = "started_at")
    private OffsetDateTime startedAt;

    @Column(name = "finished_at")
    private OffsetDateTime finishedAt;

    protected AnalysisJob() {
    }

    public AnalysisJob(Company company, LocalDate asOf, Long requestedBy) {
        this.company = company;
        this.asOf = asOf;
        this.requestedBy = requestedBy;
    }

    public UUID getId() { return id; }
    public Company getCompany() { return company; }
    public LocalDate getAsOf() { return asOf; }
    public Status getStatus() { return status; }
    public Long getRequestedBy() { return requestedBy; }
    public String getError() { return error; }
    public OffsetDateTime getCreatedAt() { return createdAt; }
    public OffsetDateTime getStartedAt() { return startedAt; }
    public OffsetDateTime getFinishedAt() { return finishedAt; }

    public boolean isActive() {
        return status == Status.QUEUED || status == Status.RUNNING;
    }

    public void start() {
        status = Status.RUNNING;
        startedAt = OffsetDateTime.now();
    }

    public void finish() {
        status = Status.DONE;
        finishedAt = OffsetDateTime.now();
    }

    public void fail(String message) {
        status = Status.FAILED;
        String m = message == null ? "unknown error" : message;
        error = m.substring(0, Math.min(m.length(), 2000));
        finishedAt = OffsetDateTime.now();
    }
}
