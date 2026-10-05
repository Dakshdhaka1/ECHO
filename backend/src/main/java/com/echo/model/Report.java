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
import java.math.BigDecimal;
import java.time.LocalDate;
import java.time.OffsetDateTime;
import java.util.UUID;
import org.hibernate.annotations.ColumnTransformer;

/** Append-only report snapshot; {@code payload} is the ML service's full AnalysisResult (JSONB). */
@Entity
@Table(name = "reports")
public class Report {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @ManyToOne(fetch = FetchType.LAZY, optional = false)
    @JoinColumn(name = "company_id")
    private Company company;

    @Column(name = "job_id")
    private UUID jobId;

    @Column(name = "as_of", nullable = false)
    private LocalDate asOf;

    @Column(name = "generated_at", nullable = false)
    private OffsetDateTime generatedAt = OffsetDateTime.now();

    @Column(name = "is_case_study", nullable = false)
    private boolean caseStudy;

    @Column(name = "health_score")
    private Short healthScore;

    private String band;

    @Column(nullable = false)
    private BigDecimal confidence;

    @Column(name = "distress_prob")
    private BigDecimal distressProb;

    @Column(name = "schema_version", nullable = false)
    private String schemaVersion;

    @Column(name = "model_version", nullable = false)
    private String modelVersion;

    @Column(name = "explanation_generator", nullable = false)
    private String explanationGenerator;

    @Column(nullable = false, columnDefinition = "jsonb")
    @ColumnTransformer(write = "?::jsonb")
    private String payload;

    protected Report() {
    }

    @SuppressWarnings("java:S107")
    public Report(Company company, UUID jobId, LocalDate asOf, boolean caseStudy, Short healthScore, String band,
                  BigDecimal confidence, BigDecimal distressProb, String schemaVersion, String modelVersion,
                  String explanationGenerator, String payload) {
        this.company = company;
        this.jobId = jobId;
        this.asOf = asOf;
        this.caseStudy = caseStudy;
        this.healthScore = healthScore;
        this.band = band;
        this.confidence = confidence;
        this.distressProb = distressProb;
        this.schemaVersion = schemaVersion;
        this.modelVersion = modelVersion;
        this.explanationGenerator = explanationGenerator;
        this.payload = payload;
    }

    public Long getId() { return id; }
    public Company getCompany() { return company; }
    public UUID getJobId() { return jobId; }
    public LocalDate getAsOf() { return asOf; }
    public OffsetDateTime getGeneratedAt() { return generatedAt; }
    public boolean isCaseStudy() { return caseStudy; }
    public Short getHealthScore() { return healthScore; }
    public String getBand() { return band; }
    public BigDecimal getConfidence() { return confidence; }
    public BigDecimal getDistressProb() { return distressProb; }
    public String getSchemaVersion() { return schemaVersion; }
    public String getModelVersion() { return modelVersion; }
    public String getExplanationGenerator() { return explanationGenerator; }
    public String getPayload() { return payload; }
}
