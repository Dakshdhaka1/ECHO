package com.echo.service;

import com.echo.config.EchoProperties;
import com.echo.dto.Dtos.CompanyDto;
import com.echo.dto.Dtos.JobDto;
import com.echo.dto.Dtos.ReportDto;
import com.echo.dto.Dtos.ReportEnvelope;
import com.echo.exception.ApiException;
import com.echo.model.AnalysisJob;
import com.echo.model.Company;
import com.echo.model.Report;
import com.echo.repository.AnalysisJobRepository;
import com.echo.repository.ReportRepository;
import java.time.Duration;
import java.time.LocalDate;
import java.time.OffsetDateTime;
import java.util.EnumSet;
import java.util.Optional;
import java.util.UUID;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.boot.context.event.ApplicationReadyEvent;
import org.springframework.context.event.EventListener;
import org.springframework.dao.DataIntegrityViolationException;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.transaction.support.TransactionSynchronization;
import org.springframework.transaction.support.TransactionSynchronizationManager;
import tools.jackson.databind.json.JsonMapper;

/**
 * Report lifecycle (ARCHITECTURE §3): serve a fresh stored report, otherwise start (or join) an async job.
 * One active job per company and as-of date is guaranteed by a partial unique index in V1.
 */
@Service
public class AnalysisService {

    private static final Logger log = LoggerFactory.getLogger(AnalysisService.class);
    private static final EnumSet<AnalysisJob.Status> ACTIVE = EnumSet.of(AnalysisJob.Status.QUEUED,
            AnalysisJob.Status.RUNNING);

    private final AnalysisJobRepository jobs;
    private final ReportRepository reports;
    private final CompanyService companies;
    private final JobRunner runner;
    private final PlanService plans;
    private final RateLimiter rateLimiter;
    private final EchoProperties props;

    public AnalysisService(AnalysisJobRepository jobs, ReportRepository reports, CompanyService companies,
                           JobRunner runner, PlanService plans, RateLimiter rateLimiter, EchoProperties props) {
        this.jobs = jobs;
        this.reports = reports;
        this.companies = companies;
        this.runner = runner;
        this.plans = plans;
        this.rateLimiter = rateLimiter;
        this.props = props;
    }

    @EventListener(ApplicationReadyEvent.class)
    @Transactional
    public void failInterruptedJobs() {
        int n = jobs.failInterruptedJobs();
        if (n > 0) {
            log.info("marked {} interrupted analysis jobs as FAILED", n);
        }
    }

    /** GET report: stored report if fresh (or historical as-of), else a running/new job (202). */
    @Transactional
    public ReportEnvelope report(Long companyId, LocalDate asOf, Long userId, String clientIp) {
        Company company = companies.get(companyId);
        Optional<Report> existing = asOf == null
                ? reports.findFirstByCompanyIdAndCaseStudyFalseOrderByGeneratedAtDesc(companyId)
                : reports.findFirstByCompanyIdAndAsOfOrderByGeneratedAtDesc(companyId, asOf);
        boolean fresh = existing.isPresent() && (asOf != null || existing.get().getGeneratedAt()
                .isAfter(OffsetDateTime.now().minus(Duration.ofHours(props.analysis().reportTtlHours()))));
        if (fresh) {
            return new ReportEnvelope("READY", toDto(existing.get(), false), null);
        }
        AnalysisJob job = submit(company, asOf, userId, clientIp, false);
        return new ReportEnvelope("PENDING", existing.map(r -> toDto(r, true)).orElse(null), JobDto.of(job, null));
    }

    /** POST analyze: explicit refresh by a logged-in user (counts against the plan's daily quota). */
    @Transactional
    public JobDto refresh(Long companyId, LocalDate asOf, Long userId) {
        return JobDto.of(submit(companies.get(companyId), asOf, userId, null, true), null);
    }

    /** Scheduler refresh of a watched company (no user quota; deduplicated like any other job). */
    @Transactional
    public JobDto systemRefresh(Long companyId) {
        return JobDto.of(submit(companies.get(companyId), null, null, null, true, true), null);
    }

    private AnalysisJob submit(Company company, LocalDate asOf, Long userId, String clientIp, boolean explicit) {
        return submit(company, asOf, userId, clientIp, explicit, false);
    }

    private AnalysisJob submit(Company company, LocalDate asOf, Long userId, String clientIp, boolean explicit,
                               boolean system) {
        LocalDate key = asOf == null ? LocalDate.now() : asOf;
        Optional<AnalysisJob> active = jobs.findFirstByCompanyIdAndAsOfAndStatusIn(company.getId(), key, ACTIVE);
        if (active.isPresent()) {
            return active.get();  // join the running job instead of starting a duplicate
        }
        if (system) {
            log.debug("system refresh of company {}", company.getId());
        } else if (userId != null) {
            plans.consumeAnalysis(userId, company.getId());
        } else if (!rateLimiter.tryAcquire("anon-analysis:" + clientIp,
                props.rateLimit().anonymousAnalysesPerHour(), Duration.ofHours(1))) {
            throw ApiException.rateLimited("Too many new analyses from this address; sign in for a higher limit.");
        }
        AnalysisJob job;
        try {
            job = jobs.saveAndFlush(new AnalysisJob(company, key, userId));
        } catch (DataIntegrityViolationException race) {
            return jobs.findFirstByCompanyIdAndAsOfAndStatusIn(company.getId(), key, ACTIVE).orElseThrow(() -> race);
        }
        UUID id = job.getId();
        TransactionSynchronizationManager.registerSynchronization(new TransactionSynchronization() {
            @Override
            public void afterCommit() {
                runner.run(id, asOf);
            }
        });
        log.info("queued job {} for company {} as of {} (explicit={})", id, company.getId(), key, explicit);
        return job;
    }

    @Transactional(readOnly = true)
    public JobDto job(UUID id) {
        AnalysisJob job = jobs.findById(id).orElseThrow(() -> ApiException.notFound("job " + id));
        Long reportId = job.getStatus() == AnalysisJob.Status.DONE
                ? reports.findFirstByCompanyIdAndAsOfOrderByGeneratedAtDesc(job.getCompany().getId(), job.getAsOf())
                    .or(() -> reports.findFirstByCompanyIdAndCaseStudyFalseOrderByGeneratedAtDesc(job.getCompany().getId()))
                    .map(Report::getId).orElse(null)
                : null;
        return JobDto.of(job, reportId);
    }

    @Transactional(readOnly = true)
    public ReportDto reportById(Long reportId) {
        return toDto(reports.findById(reportId).orElseThrow(() -> ApiException.notFound("report " + reportId)), false);
    }

    public ReportDto toDto(Report r, boolean stale) {
        return new ReportDto(r.getId(), CompanyDto.of(r.getCompany()), r.getAsOf(), r.getGeneratedAt(), r.isCaseStudy(),
                r.getHealthScore(), r.getBand(), r.getConfidence(), r.getDistressProb(), r.getModelVersion(),
                r.getExplanationGenerator(), stale, JsonMapper.shared().readTree(r.getPayload()));
    }
}
