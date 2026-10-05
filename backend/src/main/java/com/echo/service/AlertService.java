package com.echo.service;

import com.echo.model.Alert;
import com.echo.model.Report;
import com.echo.repository.AlertRepository;
import com.echo.repository.WatchlistItemRepository;
import java.util.HashSet;
import java.util.List;
import java.util.Optional;
import java.util.Set;
import org.springframework.stereotype.Service;
import tools.jackson.databind.JsonNode;
import tools.jackson.databind.json.JsonMapper;

/**
 * Watchlist alerts raised when a new report is stored: a score drop at or above the user's threshold
 * (SCORING §6 SCORE_DROP) and newly appearing HIGH/CRITICAL warning signals.
 */
@Service
public class AlertService {

    private final WatchlistItemRepository items;
    private final AlertRepository alerts;

    public AlertService(WatchlistItemRepository items, AlertRepository alerts) {
        this.items = items;
        this.alerts = alerts;
    }

    public void evaluate(Report report, JsonNode current, Optional<Report> previous) {
        List<Object[]> watchers = items.findWatchers(report.getCompany().getId());
        if (watchers.isEmpty()) {
            return;
        }
        JsonNode prevTree = previous.map(p -> JsonMapper.shared().readTree(p.getPayload())).orElse(null);
        Set<String> prevSignals = new HashSet<>();
        if (prevTree != null) {
            prevTree.path("signals").forEach(s -> prevSignals.add(s.path("code").asString()));
        }
        String name = report.getCompany().getName();
        for (Object[] w : watchers) {
            Long userId = (Long) w[0];
            int threshold = ((Number) w[1]).intValue();
            Short now = report.getHealthScore();
            Short before = previous.map(Report::getHealthScore).orElse(null);
            if (now != null && before != null && before - now >= threshold) {
                int drop = before - now;
                alerts.save(new Alert(userId, report.getCompany(), report.getId(), "SCORE_DROP",
                        drop >= 2 * threshold ? "HIGH" : "MEDIUM",
                        name + " health score fell " + drop + " points (" + before + " -> " + now + ", "
                                + report.getBand() + ")."));
            }
            for (JsonNode s : current.path("signals")) {
                String severity = s.path("severity").asString();
                boolean serious = "CRITICAL".equals(severity) || "HIGH".equals(severity);
                boolean isNew = prevTree == null ? "CRITICAL".equals(severity) : !prevSignals.contains(s.path("code").asString());
                if (serious && isNew) {
                    alerts.save(new Alert(userId, report.getCompany(), report.getId(), "NEW_SIGNAL", severity,
                            name + ": " + s.path("message").asString()));
                }
            }
        }
    }
}
