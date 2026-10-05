package com.echo.service;

import com.echo.client.MlServiceClient;
import com.echo.model.AnalysisJob;
import com.echo.model.Company;
import com.echo.model.Report;
import com.echo.model.ScorePoint;
import com.echo.repository.AnalysisJobRepository;
import com.echo.repository.CompanyRepository;
import com.echo.repository.ReportRepository;
import com.echo.repository.ScorePointRepository;
import java.math.BigDecimal;
import java.math.RoundingMode;
import java.time.LocalDate;
import java.util.Optional;
import java.util.UUID;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.scheduling.annotation.Async;
import org.springframework.stereotype.Service;
import org.springframework.transaction.support.TransactionTemplate;
import tools.jackson.databind.JsonNode;
import tools.jackson.databind.json.JsonMapper;
import tools.jackson.databind.node.ObjectNode;

/** Executes one analysis job: ML call outside any transaction, then persistence + alerts in one transaction. */
@Service
public class JobRunner {

    private static final Logger log = LoggerFactory.getLogger(JobRunner.class);

    private final AnalysisJobRepository jobs;
    private final ReportRepository reports;
    private final ScorePointRepository points;
    private final CompanyRepository companies;
    private final MlServiceClient ml;
    private final AlertService alerts;
    private final TransactionTemplate tx;

    public JobRunner(AnalysisJobRepository jobs, ReportRepository reports, ScorePointRepository points,
                     CompanyRepository companies, MlServiceClient ml, AlertService alerts, TransactionTemplate tx) {
        this.jobs = jobs;
        this.reports = reports;
        this.points = points;
        this.companies = companies;
        this.ml = ml;
        this.alerts = alerts;
        this.tx = tx;
    }

    /** explicitAsOf=null analyses "latest" (today in live mode, the recorded snapshot date in demo mode). */
    @Async("analysisExecutor")
    public void run(UUID jobId, LocalDate explicitAsOf) {
        Company company = tx.execute(s -> {
            AnalysisJob job = jobs.findById(jobId).orElseThrow();
            job.start();
            Company c = job.getCompany();
            c.getName(); // initialise the lazy proxy inside the transaction
            return c;
        });
        try {
            MlServiceClient.Analysis analysis = ml.analyze(company.getMarket(), company.getMarketId(),
                    company.getTicker(), company.getName(), explicitAsOf, true);
            Long reportId = tx.execute(s -> persist(jobId, company.getId(), analysis));
            log.info("job {} done: company {} -> report {}", jobId, company.getId(), reportId);
        } catch (RuntimeException e) {
            log.warn("job {} failed: {}", jobId, e.getMessage());
            tx.executeWithoutResult(s -> jobs.findById(jobId).ifPresent(j -> j.fail(e.getMessage())));
        }
    }

    private Long persist(UUID jobId, Long companyId, MlServiceClient.Analysis analysis) {
        JsonNode t = analysis.tree();
        Company company = companies.findById(companyId).orElseThrow();
        JsonNode c = t.path("company");
        company.updateIdentity(c.path("name").asString(null), c.path("ticker").asString(null), null);
        company.updateProfile(c.path("sector").asString(null), c.path("sic").asString(null),
                c.path("exchange").asString(null));

        LocalDate asOf = LocalDate.parse(t.path("as_of").asString());
        JsonNode health = t.path("health");
        Short score = health.path("score").isNumber() ? (short) health.path("score").asInt() : null;
        BigDecimal confidence = decimal(health.path("confidence"), 3).orElse(BigDecimal.ZERO);
        JsonNode distress = t.path("distress");
        BigDecimal prob = distress.path("available").asBoolean(false)
                ? decimal(distress.path("probability_12m"), 4).orElse(null) : null;
        boolean caseStudy = t.path("case_study").isObject();
        Optional<Report> previous = caseStudy ? Optional.empty()
                : reports.findFirstByCompanyIdAndCaseStudyFalseOrderByGeneratedAtDesc(companyId);

        Report report = reports.save(new Report(company, jobId, asOf, caseStudy, score, health.path("band").asString(),
                confidence, prob, t.path("schema_version").asString(), t.path("model_version").asString(),
                t.path("summary").path("generator").asString("template"), analysis.json()));

        upsertPoint(companyId, asOf, score, confidence, pillarSummary(t), "LIVE", report.getId(), true);
        for (JsonNode h : t.path("history")) {
            if (!h.path("partial_score").isNumber()) continue;
            ObjectNode pillars = JsonMapper.shared().createObjectNode();
            pillars.put("partial", true);
            pillars.set("financial", h.path("financial"));
            pillars.set("events", h.path("events"));
            pillars.set("distress_probability", h.path("distress_probability"));
            upsertPoint(companyId, LocalDate.parse(h.path("as_of").asString()),
                    (short) Math.round(h.path("partial_score").asDouble()), new BigDecimal("0.450"), pillars.toString(),
                    "BACKFILL", null, false);
        }
        jobs.findById(jobId).ifPresent(AnalysisJob::finish);
        if (!caseStudy) {
            alerts.evaluate(report, t, previous);
        }
        return report.getId();
    }

    private void upsertPoint(Long companyId, LocalDate asOf, Short score, BigDecimal confidence, String pillars,
                             String source, Long reportId, boolean overwrite) {
        ScorePoint.Key key = new ScorePoint.Key(companyId, asOf);
        Optional<ScorePoint> existing = points.findById(key);
        if (existing.isPresent()) {
            // a LIVE point is never replaced by a partial BACKFILL point
            if (overwrite || "BACKFILL".equals(existing.get().getSource())) {
                existing.get().update(score, confidence, pillars, source, reportId);
            }
            return;
        }
        points.save(new ScorePoint(key, score, confidence, pillars, source, reportId));
    }

    private static String pillarSummary(JsonNode t) {
        ObjectNode out = JsonMapper.shared().createObjectNode();
        for (JsonNode p : t.path("pillars")) {
            out.set(p.path("key").asString(), p.path("score"));
        }
        out.set("distress_probability", t.path("distress").path("probability_12m"));
        return out.toString();
    }

    private static Optional<BigDecimal> decimal(JsonNode n, int scale) {
        return n.isNumber() ? Optional.of(BigDecimal.valueOf(n.asDouble()).setScale(scale, RoundingMode.HALF_UP))
                : Optional.empty();
    }
}
