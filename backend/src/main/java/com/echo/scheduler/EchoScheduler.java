package com.echo.scheduler;

import com.echo.client.MlServiceClient;
import com.echo.config.EchoProperties;
import com.echo.model.Company;
import com.echo.repository.CompanyRepository;
import com.echo.service.AnalysisService;
import java.util.List;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.scheduling.annotation.Scheduled;
import org.springframework.stereotype.Component;
import tools.jackson.databind.JsonNode;

/**
 * Background operations (ML_PIPELINE §7.4): daily re-analysis of watched companies (drives SCORE_DROP alerts),
 * weekly drift/freshness monitoring with retraining when drift is detected, and monthly scheduled retraining.
 */
@Component
@ConditionalOnProperty(prefix = "echo.scheduler", name = "enabled", havingValue = "true", matchIfMissing = true)
public class EchoScheduler {

    private static final Logger log = LoggerFactory.getLogger(EchoScheduler.class);
    /** Models retrained on the monthly schedule (the gate decides whether each new version is promoted). */
    static final List<String> SCHEDULED_MODELS = List.of("distress", "financial_anomaly", "peer_clusters",
            "revenue_forecast", "ocf_forecast", "market_anomaly", "news_sentiment", "review_sentiment");

    private final CompanyRepository companies;
    private final AnalysisService analysis;
    private final MlServiceClient ml;
    private final EchoProperties props;

    public EchoScheduler(CompanyRepository companies, AnalysisService analysis, MlServiceClient ml, EchoProperties props) {
        this.companies = companies;
        this.analysis = analysis;
        this.ml = ml;
        this.props = props;
    }

    @Scheduled(cron = "${echo.scheduler.watchlist-refresh-cron}")
    public void refreshWatchedCompanies() {
        List<Company> watched = companies.findWatched();
        log.info("scheduled refresh of {} watched companies", watched.size());
        for (Company c : watched) {
            try {
                analysis.systemRefresh(c.getId());
            } catch (RuntimeException e) {
                log.warn("refresh of company {} not queued: {}", c.getId(), e.getMessage());
            }
        }
    }

    @Scheduled(cron = "${echo.scheduler.monitoring-cron}")
    public void monitorAndRetrainOnDrift() {
        try {
            JsonNode report = ml.runMonitoring();
            JsonNode drifted = report.path("retrain_recommended");
            log.info("monitoring: {} inferences, drift in {}", report.path("rows").asInt(), drifted);
            if (props.scheduler().autoRetrainOnDrift()) {
                drifted.forEach(m -> ml.retrain(m.asString(), true));
            }
        } catch (RuntimeException e) {
            log.warn("monitoring run failed: {}", e.getMessage());
        }
    }

    @Scheduled(cron = "${echo.scheduler.retrain-cron}")
    public void scheduledRetraining() {
        for (String model : SCHEDULED_MODELS) {
            try {
                // the promotion gate inside the ML service decides whether the new version replaces the champion
                ml.retrain(model, true);
            } catch (RuntimeException e) {
                log.warn("scheduled retraining of {} not started: {}", model, e.getMessage());
            }
        }
    }
}
