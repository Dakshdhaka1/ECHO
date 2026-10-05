package com.echo.service;

import com.echo.dto.Dtos.CompanyDto;
import com.echo.dto.Dtos.CompareItemDto;
import com.echo.dto.Dtos.HistoryPointDto;
import com.echo.dto.Dtos.RadarDto;
import com.echo.dto.Dtos.RadarPendingDto;
import com.echo.dto.Dtos.RadarPointDto;
import com.echo.exception.ApiException;
import com.echo.model.Company;
import com.echo.model.Plan;
import com.echo.model.Report;
import com.echo.repository.ReportRepository;
import com.echo.repository.ScorePointRepository;
import java.time.LocalDate;
import java.util.ArrayList;
import java.util.List;
import java.util.Optional;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;
import tools.jackson.databind.JsonNode;
import tools.jackson.databind.json.JsonMapper;

/** Score history and company comparison, both limited by the caller's plan. */
@Service
public class InsightService {

    private final ScorePointRepository points;
    private final ReportRepository reports;
    private final CompanyService companies;
    private final PlanService plans;

    public InsightService(ScorePointRepository points, ReportRepository reports, CompanyService companies,
                          PlanService plans) {
        this.points = points;
        this.reports = reports;
        this.companies = companies;
        this.plans = plans;
    }

    @Transactional(readOnly = true)
    public List<HistoryPointDto> history(Long companyId, LocalDate from, LocalDate to, Long userId) {
        companies.get(companyId);
        Plan plan = plans.planOf(userId);
        LocalDate end = to == null ? LocalDate.now() : to;
        LocalDate start = from == null ? end.minusYears(5) : from;
        if (plan.historyDays() > 0 && start.isBefore(end.minusDays(plan.historyDays()))) {
            start = end.minusDays(plan.historyDays());  // Free plan: last 12 months only
        }
        return points.findByIdCompanyIdAndIdAsOfBetweenOrderByIdAsOfAsc(companyId, start, end).stream()
                .map(p -> new HistoryPointDto(p.getId().getAsOf(), p.getHealthScore(), p.getConfidence(),
                        p.getSource(), JsonMapper.shared().readTree(p.getPillars())))
                .toList();
    }

    @Transactional(readOnly = true)
    public List<CompareItemDto> compare(List<Long> companyIds, Long userId) {
        Plan plan = plans.planOf(userId);
        if (companyIds.isEmpty()) {
            throw ApiException.badRequest("Pass at least one company id.");
        }
        if (companyIds.size() > plan.maxCompare()) {
            throw ApiException.planLimit("The " + plan.label() + " plan compares up to " + plan.maxCompare()
                    + " companies at once.");
        }
        List<CompareItemDto> out = new ArrayList<>();
        for (Long id : companyIds) {
            Company c = companies.get(id);
            Report r = reports.findFirstByCompanyIdAndCaseStudyFalseOrderByGeneratedAtDesc(id).orElse(null);
            if (r == null) {
                out.add(new CompareItemDto(CompanyDto.of(c), null, null, null, null, null, null, null, null, 0));
                continue;
            }
            JsonNode t = JsonMapper.shared().readTree(r.getPayload());
            out.add(new CompareItemDto(CompanyDto.of(c), r.getId(), r.getAsOf(), r.getHealthScore(), r.getBand(),
                    r.getConfidence(), r.getDistressProb(), t.path("pillars"), t.path("segment"),
                    t.path("signals").size()));
        }
        return out;
    }

    /**
     * Latest stored report for every (company, as-of) pair of the demo universe: live reports for "latest",
     * point-in-time reports for case-study dates. Read-only: never starts an analysis.
     */
    public RadarDto radar() {
        List<RadarPointDto> points = new ArrayList<>();
        List<RadarPendingDto> pending = new ArrayList<>();
        java.util.Set<Long> seenReports = new java.util.HashSet<>();  // a live report can coincide with a case-study date
        for (JsonNode u : companies.universe()) {
            long id = u.path("companyId").asLong();
            for (JsonNode a : u.path("asOf")) {
                String asOf = a.asString();
                boolean latest = "latest".equals(asOf);
                Optional<Report> report = latest
                        ? reports.findFirstByCompanyIdAndCaseStudyFalseOrderByGeneratedAtDesc(id)
                        : reports.findFirstByCompanyIdAndAsOfOrderByGeneratedAtDesc(id, LocalDate.parse(asOf));
                if (report.isEmpty()) {
                    pending.add(new RadarPendingDto(id, u.path("ticker").asString(null), asOf));
                    continue;
                }
                Report r = report.get();
                if (!seenReports.add(r.getId())) {
                    continue;
                }
                JsonNode t = JsonMapper.shared().readTree(r.getPayload());
                JsonNode baseRate = t.path("distress").path("base_rate");
                Double financial = null;
                for (JsonNode p : t.path("pillars")) {
                    if ("financial".equals(p.path("key").asString()) && p.path("score").isNumber()) {
                        financial = p.path("score").asDouble();
                    }
                }
                points.add(new RadarPointDto(id, u.path("ticker").asString(null), u.path("name").asString(),
                        u.path("role").asString(), !latest, r.getAsOf(), r.getId(), r.getHealthScore(), r.getBand(),
                        r.getConfidence(), r.getDistressProb(), baseRate.isNumber() ? baseRate.asDouble() : null,
                        t.path("distress").path("unavailable_reason").asString(null), financial, t.path("signals").size()));
            }
        }
        return new RadarDto(points, pending);
    }
}
