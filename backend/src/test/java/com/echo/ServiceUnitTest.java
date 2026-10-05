package com.echo;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.ArgumentMatchers.anyString;
import static org.mockito.ArgumentMatchers.eq;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.never;
import static org.mockito.Mockito.times;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

import com.echo.config.EchoProperties;
import com.echo.config.SecretsGuard;
import com.echo.exception.ApiException;
import com.echo.model.Alert;
import com.echo.model.Company;
import com.echo.model.Plan;
import com.echo.model.Report;
import com.echo.model.UsageEvent;
import com.echo.model.User;
import com.echo.repository.AlertRepository;
import com.echo.repository.ReportRepository;
import com.echo.repository.ScorePointRepository;
import com.echo.repository.UsageEventRepository;
import com.echo.repository.UserRepository;
import com.echo.repository.WatchlistItemRepository;
import com.echo.service.AlertService;
import com.echo.service.CompanyService;
import com.echo.service.InsightService;
import com.echo.service.PlanService;
import com.echo.service.RateLimiter;
import java.time.Duration;
import java.time.LocalDate;
import java.util.List;
import java.util.Optional;
import org.junit.jupiter.api.Test;
import org.mockito.ArgumentCaptor;
import org.springframework.data.redis.core.StringRedisTemplate;
import org.springframework.data.redis.core.ValueOperations;
import tools.jackson.databind.JsonNode;
import tools.jackson.databind.json.JsonMapper;

/** Fast unit tests of the business rules (no Spring context, no database). */
class ServiceUnitTest {

    // ------------------------------------------------------------------------------------------ plans
    @Test
    void anonymousUsersGetTheFreePlan() {
        PlanService plans = new PlanService(mock(UserRepository.class), mock(UsageEventRepository.class));
        assertThat(plans.planOf(null)).isEqualTo(Plan.FREE);
    }

    @Test
    void analysisQuotaIsEnforcedPerPlan() {
        UserRepository users = mock(UserRepository.class);
        UsageEventRepository usage = mock(UsageEventRepository.class);
        User user = mock(User.class);
        when(user.getPlan()).thenReturn(Plan.FREE);
        when(users.findById(7L)).thenReturn(Optional.of(user));
        PlanService plans = new PlanService(users, usage);

        when(usage.countByUserIdAndKindAndCreatedAtAfter(eq(7L), eq(UsageEvent.ANALYSIS), any())).thenReturn(4L);
        plans.consumeAnalysis(7L, 1L);
        verify(usage, times(1)).save(any(UsageEvent.class));

        when(usage.countByUserIdAndKindAndCreatedAtAfter(eq(7L), eq(UsageEvent.ANALYSIS), any()))
                .thenReturn((long) Plan.FREE.analysesPerDay());
        assertThatThrownBy(() -> plans.consumeAnalysis(7L, 1L))
                .isInstanceOf(ApiException.class)
                .satisfies(e -> assertThat(((ApiException) e).getType()).isEqualTo("plan-limit"));
        verify(usage, times(1)).save(any(UsageEvent.class));
    }

    @Test
    void paidPlansStrictlyExtendTheFreePlan() {
        for (Plan p : List.of(Plan.PRO, Plan.ENTERPRISE)) {
            assertThat(p.analysesPerDay()).isGreaterThan(Plan.FREE.analysesPerDay());
            assertThat(p.maxCompare()).isGreaterThan(Plan.FREE.maxCompare());
            assertThat(p.pdfExport()).isTrue();
            assertThat(p.historyDays()).isNegative();  // unlimited history
        }
        assertThat(Plan.FREE.maxApiKeys()).isZero();
    }

    // ------------------------------------------------------------------------------------------ rate limiting
    @Test
    @SuppressWarnings("unchecked")
    void rateLimiterAllowsUpToTheLimitInRedis() {
        StringRedisTemplate redis = mock(StringRedisTemplate.class);
        ValueOperations<String, String> ops = mock(ValueOperations.class);
        when(redis.opsForValue()).thenReturn(ops);
        when(ops.increment(anyString())).thenReturn(1L, 2L, 3L);
        RateLimiter limiter = new RateLimiter(redis);

        assertThat(limiter.tryAcquire("ip:1", 2, Duration.ofHours(1))).isTrue();
        assertThat(limiter.tryAcquire("ip:1", 2, Duration.ofHours(1))).isTrue();
        assertThat(limiter.tryAcquire("ip:1", 2, Duration.ofHours(1))).isFalse();
        verify(redis, times(1)).expire(anyString(), eq(Duration.ofHours(1)));  // TTL set once per window
    }

    @Test
    void rateLimiterFallsBackToLocalCountersWhenRedisIsDown() {
        StringRedisTemplate redis = mock(StringRedisTemplate.class);
        when(redis.opsForValue()).thenThrow(new IllegalStateException("connection refused"));
        RateLimiter limiter = new RateLimiter(redis);

        assertThat(limiter.tryAcquire("ip:2", 2, Duration.ofHours(1))).isTrue();
        assertThat(limiter.tryAcquire("ip:2", 2, Duration.ofHours(1))).isTrue();
        assertThat(limiter.tryAcquire("ip:2", 2, Duration.ofHours(1))).isFalse();
        assertThat(limiter.tryAcquire("ip:3", 2, Duration.ofHours(1))).isTrue();  // keys are independent
    }

    // ------------------------------------------------------------------------------------------ alerts
    private static Report report(short score, String band) {
        Company company = mock(Company.class);
        when(company.getId()).thenReturn(1L);
        when(company.getName()).thenReturn("Northwind Holdings Inc.");
        Report r = mock(Report.class);
        when(r.getCompany()).thenReturn(company);
        when(r.getHealthScore()).thenReturn(score);
        when(r.getBand()).thenReturn(band);
        when(r.getPayload()).thenReturn("{\"signals\":[]}");
        return r;
    }

    private static JsonNode signals(String json) {
        return JsonMapper.shared().readTree("{\"signals\":" + json + "}");
    }

    @Test
    void scoreDropAtOrAboveTheThresholdRaisesAnAlert() {
        WatchlistItemRepository items = mock(WatchlistItemRepository.class);
        AlertRepository alerts = mock(AlertRepository.class);
        when(items.findWatchers(1L)).thenReturn(List.<Object[]>of(new Object[] {42L, 10}));
        AlertService service = new AlertService(items, alerts);

        service.evaluate(report((short) 48, "WATCH"), signals("[]"), Optional.of(report((short) 70, "STRONG")));
        ArgumentCaptor<Alert> saved = ArgumentCaptor.forClass(Alert.class);
        verify(alerts).save(saved.capture());
        assertThat(saved.getValue().getType()).isEqualTo("SCORE_DROP");
        assertThat(saved.getValue().getSeverity()).isEqualTo("HIGH");  // 22-point drop >= 2x threshold
        assertThat(saved.getValue().getUserId()).isEqualTo(42L);
    }

    @Test
    void smallDropsAndKnownSignalsDoNotAlert() {
        WatchlistItemRepository items = mock(WatchlistItemRepository.class);
        AlertRepository alerts = mock(AlertRepository.class);
        when(items.findWatchers(1L)).thenReturn(List.<Object[]>of(new Object[] {42L, 10}));
        AlertService service = new AlertService(items, alerts);
        Report previous = report((short) 70, "STRONG");
        when(previous.getPayload()).thenReturn("{\"signals\":[{\"code\":\"GOING_CONCERN\",\"severity\":\"HIGH\"}]}");

        service.evaluate(report((short) 65, "STABLE"),
                signals("[{\"code\":\"GOING_CONCERN\",\"severity\":\"HIGH\",\"message\":\"m\"}]"), Optional.of(previous));
        verify(alerts, never()).save(any());
    }

    @Test
    void newHighSeveritySignalRaisesAnAlert() {
        WatchlistItemRepository items = mock(WatchlistItemRepository.class);
        AlertRepository alerts = mock(AlertRepository.class);
        when(items.findWatchers(1L)).thenReturn(List.<Object[]>of(new Object[] {42L, 10}));
        AlertService service = new AlertService(items, alerts);

        service.evaluate(report((short) 66, "STABLE"),
                signals("[{\"code\":\"AUDITOR_CHANGE\",\"severity\":\"HIGH\",\"message\":\"Auditor resigned\"}]"),
                Optional.of(report((short) 67, "STABLE")));
        ArgumentCaptor<Alert> saved = ArgumentCaptor.forClass(Alert.class);
        verify(alerts).save(saved.capture());
        assertThat(saved.getValue().getType()).isEqualTo("NEW_SIGNAL");
        assertThat(saved.getValue().getMessage()).contains("Auditor resigned");
    }

    // ------------------------------------------------------------------------------------------ secrets
    private static EchoProperties props(boolean demo, String jwt, String adminToken) {
        return new EchoProperties("http://ml", demo, adminToken, List.of(), new EchoProperties.Jwt(jwt, 60, "echo"),
                null, null, null, null);
    }

    @Test
    void secretsGuardRejectsPlaceholdersOutsideDemoMode() {
        String placeholderJwt = "change_me_to_a_long_random_string_of_at_least_32_bytes";
        assertThatThrownBy(() -> new SecretsGuard(props(false, placeholderJwt, "real-token"), "real-db").check())
                .isInstanceOf(IllegalStateException.class)
                .hasMessageContaining("JWT_SECRET");
        new SecretsGuard(props(true, placeholderJwt, "change_me_admin_token"), "change_me").check();  // demo: warn only
        new SecretsGuard(props(false, "a-very-long-real-secret-value-of-48-bytes-xxxxxx", "real-token"), "real-db").check();
    }

    // ------------------------------------------------------------------------------------------ radar
    @Test
    void radarReturnsStoredReportsAndListsUnanalysedPairs() {
        CompanyService companies = mock(CompanyService.class);
        ReportRepository reports = mock(ReportRepository.class);
        JsonNode apple = JsonMapper.shared().readTree(
                "{\"companyId\":1,\"ticker\":\"AAPL\",\"name\":\"Apple Inc.\",\"role\":\"healthy\",\"asOf\":[\"latest\"]}");
        JsonNode bbby = JsonMapper.shared().readTree(
                "{\"companyId\":10,\"ticker\":\"BBBY\",\"name\":\"Bed Bath\",\"role\":\"historical_distress\","
                        + "\"asOf\":[\"2022-04-30\",\"2023-01-31\"]}");
        when(companies.universe()).thenReturn(List.of(apple, bbby));
        Report live = report((short) 68, "STABLE");
        when(live.getPayload()).thenReturn("{\"signals\":[],\"distress\":{\"base_rate\":0.012},"
                + "\"pillars\":[{\"key\":\"financial\",\"score\":69.9}]}");
        when(live.getId()).thenReturn(101L);
        Report caseStudy = report((short) 21, "CRITICAL");
        when(caseStudy.getId()).thenReturn(102L);
        when(caseStudy.getAsOf()).thenReturn(LocalDate.parse("2023-01-31"));
        when(caseStudy.getPayload()).thenReturn("{\"signals\":[{\"code\":\"GOING_CONCERN\"}],\"pillars\":[]}");
        when(reports.findFirstByCompanyIdAndCaseStudyFalseOrderByGeneratedAtDesc(1L)).thenReturn(Optional.of(live));
        when(reports.findFirstByCompanyIdAndAsOfOrderByGeneratedAtDesc(10L, LocalDate.parse("2022-04-30"))).thenReturn(Optional.empty());
        when(reports.findFirstByCompanyIdAndAsOfOrderByGeneratedAtDesc(10L, LocalDate.parse("2023-01-31"))).thenReturn(Optional.of(caseStudy));

        var radar = new InsightService(mock(ScorePointRepository.class), reports, companies, mock(PlanService.class)).radar();
        assertThat(radar.points()).hasSize(2);
        assertThat(radar.points().get(0).financialScore()).isEqualTo(69.9);
        assertThat(radar.points().get(0).distressBaseRate()).isEqualTo(0.012);
        assertThat(radar.points().get(0).caseStudy()).isFalse();
        assertThat(radar.points().get(1).caseStudy()).isTrue();
        assertThat(radar.points().get(1).signals()).isEqualTo(1);
        assertThat(radar.pending()).singleElement().satisfies(p -> assertThat(p.asOf()).isEqualTo("2022-04-30"));
    }
}
