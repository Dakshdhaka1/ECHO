package com.echo.model;

import jakarta.persistence.Column;
import jakarta.persistence.Embeddable;
import jakarta.persistence.EmbeddedId;
import jakarta.persistence.Entity;
import jakarta.persistence.Table;
import java.io.Serializable;
import java.math.BigDecimal;
import java.time.LocalDate;
import java.util.Objects;
import org.hibernate.annotations.ColumnTransformer;

/** One point of a company's score history (LIVE reports, or point-in-time BACKFILL from the ML service). */
@Entity
@Table(name = "score_points")
public class ScorePoint {

    @Embeddable
    public static class Key implements Serializable {
        @Column(name = "company_id")
        private Long companyId;

        @Column(name = "as_of")
        private LocalDate asOf;

        protected Key() {
        }

        public Key(Long companyId, LocalDate asOf) {
            this.companyId = companyId;
            this.asOf = asOf;
        }

        public Long getCompanyId() { return companyId; }
        public LocalDate getAsOf() { return asOf; }

        @Override
        public boolean equals(Object o) {
            return o instanceof Key k && Objects.equals(companyId, k.companyId) && Objects.equals(asOf, k.asOf);
        }

        @Override
        public int hashCode() {
            return Objects.hash(companyId, asOf);
        }
    }

    @EmbeddedId
    private Key id;

    @Column(name = "health_score")
    private Short healthScore;

    @Column(nullable = false)
    private BigDecimal confidence;

    @Column(nullable = false, columnDefinition = "jsonb")
    @ColumnTransformer(write = "?::jsonb")
    private String pillars;

    @Column(nullable = false)
    private String source;

    @Column(name = "report_id")
    private Long reportId;

    protected ScorePoint() {
    }

    public ScorePoint(Key id, Short healthScore, BigDecimal confidence, String pillars, String source, Long reportId) {
        this.id = id;
        update(healthScore, confidence, pillars, source, reportId);
    }

    public final void update(Short score, BigDecimal conf, String pillarsJson, String src, Long report) {
        this.healthScore = score;
        this.confidence = conf;
        this.pillars = pillarsJson;
        this.source = src;
        this.reportId = report;
    }

    public Key getId() { return id; }
    public Short getHealthScore() { return healthScore; }
    public BigDecimal getConfidence() { return confidence; }
    public String getPillars() { return pillars; }
    public String getSource() { return source; }
    public Long getReportId() { return reportId; }
}
