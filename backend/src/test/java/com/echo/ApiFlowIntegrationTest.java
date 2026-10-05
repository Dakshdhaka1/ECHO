package com.echo;

import static org.assertj.core.api.Assertions.assertThat;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.ArgumentMatchers.anyBoolean;
import static org.mockito.ArgumentMatchers.anyInt;
import static org.mockito.ArgumentMatchers.anyString;
import static org.mockito.Mockito.when;

import com.echo.client.MlServiceClient;
import java.nio.charset.StandardCharsets;
import java.time.LocalDate;
import java.util.Map;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.web.server.LocalServerPort;
import org.springframework.boot.testcontainers.service.connection.ServiceConnection;
import org.springframework.core.io.ClassPathResource;
import org.springframework.http.HttpMethod;
import org.springframework.http.MediaType;
import org.springframework.test.context.ActiveProfiles;
import org.springframework.test.context.bean.override.mockito.MockitoBean;
import org.springframework.web.client.RestClient;
import org.testcontainers.junit.jupiter.Container;
import org.testcontainers.junit.jupiter.Testcontainers;
import org.testcontainers.postgresql.PostgreSQLContainer;
import tools.jackson.databind.JsonNode;
import tools.jackson.databind.json.JsonMapper;
import tools.jackson.databind.node.ObjectNode;

/**
 * End-to-end API flow against real PostgreSQL: auth -> search -> async analysis job -> report -> history ->
 * watchlist + score-drop alert -> exports with plan limits -> demo billing -> API key access -> admin RBAC.
 * Only the ML service is stubbed, using a real AnalysisResult recorded from the ML service as the contract fixture.
 */
@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
@ActiveProfiles("test")
@Testcontainers
class ApiFlowIntegrationTest {

    @Container
    @ServiceConnection
    static PostgreSQLContainer postgres = new PostgreSQLContainer("postgres:16-alpine");

    @LocalServerPort
    int port;

    @MockitoBean
    MlServiceClient ml;

    RestClient http;
    String fixture;

    record Res(int status, JsonNode body, byte[] raw) {
    }

    @BeforeEach
    void setUp() throws Exception {
        http = RestClient.create("http://localhost:" + port);
        fixture = new ClassPathResource("analysis-apple.json").getContentAsString(StandardCharsets.UTF_8);
        ObjectNode candidate = JsonMapper.shared().createObjectNode()
                .put("market", "US_SEC").put("market_id", "0000320193").put("name", "Apple Inc.")
                .put("ticker", "AAPL").put("match_score", 1.0).put("is_demo", true);
        candidate.putArray("former_names").add("APPLE COMPUTER INC");
        when(ml.resolve(anyString(), anyInt())).thenReturn(JsonMapper.shared().createArrayNode().add(candidate));
        when(ml.analyze(anyString(), anyString(), any(), any(), any(), anyBoolean()))
                .thenReturn(analysis(fixture));
    }

    static MlServiceClient.Analysis analysis(String json) {
        return new MlServiceClient.Analysis(json, JsonMapper.shared().readTree(json));
    }

    Res call(HttpMethod method, String path, Object body, String token, String apiKey) {
        var spec = http.method(method).uri(path);
        if (token != null) spec = spec.header("Authorization", "Bearer " + token);
        if (apiKey != null) spec = spec.header("X-API-Key", apiKey);
        if (body != null) spec = spec.contentType(MediaType.APPLICATION_JSON).body(body);
        return spec.exchange((req, res) -> {
            byte[] raw = res.getBody().readAllBytes();
            JsonNode node = null;
            String ct = String.valueOf(res.getHeaders().getContentType());
            if (raw.length > 0 && ct.contains("json")) node = JsonMapper.shared().readTree(raw);
            return new Res(res.getStatusCode().value(), node, raw);
        });
    }

    Res get(String path, String token) {
        return call(HttpMethod.GET, path, null, token, null);
    }

    String register(String email) {
        Res r = call(HttpMethod.POST, "/api/auth/register",
                Map.of("email", email, "password", "correct horse battery", "displayName", "Tester"), null, null);
        assertThat(r.status()).isEqualTo(201);
        return r.body().path("token").asString();
    }

    long awaitJob(String jobId) throws InterruptedException {
        for (int i = 0; i < 100; i++) {
            JsonNode job = get("/api/jobs/" + jobId, null).body();
            if ("DONE".equals(job.path("status").asString())) return job.path("reportId").asLong();
            assertThat(job.path("status").asString()).isNotEqualTo("FAILED");
            Thread.sleep(100);
        }
        throw new AssertionError("job did not finish");
    }

    @Test
    void fullUserJourney() throws Exception {
        String token = register("analyst@test.dev");

        // search -> company id
        Res search = get("/api/companies/search?q=apple", null);
        assertThat(search.status()).isEqualTo(200);
        long companyId = search.body().get(0).path("company").path("id").asLong();
        assertThat(search.body().get(0).path("formerNames").get(0).asString()).isEqualTo("APPLE COMPUTER INC");

        // first report request starts an async job (202), then the report is served (200)
        Res pending = get("/api/companies/" + companyId + "/report", null);
        assertThat(pending.status()).isEqualTo(202);
        long reportId = awaitJob(pending.body().path("job").path("id").asString());
        Res ready = get("/api/companies/" + companyId + "/report", null);
        assertThat(ready.status()).isEqualTo(200);
        assertThat(ready.body().path("report").path("id").asLong()).isEqualTo(reportId);
        assertThat(ready.body().path("report").path("healthScore").asInt()).isEqualTo(77);
        assertThat(ready.body().path("report").path("payload").path("pillars").size()).isEqualTo(5);

        // history: one LIVE point plus point-in-time BACKFILL points
        JsonNode history = get("/api/companies/" + companyId + "/history?from=2020-01-01", token).body();
        assertThat(history).anyMatch(p -> "LIVE".equals(p.path("source").asString()));
        assertThat(history).anyMatch(p -> "BACKFILL".equals(p.path("source").asString()));

        // watchlist + a refreshed report with a lower score -> SCORE_DROP alert
        long watchlistId = get("/api/watchlists", token).body().get(0).path("id").asLong();
        Res added = call(HttpMethod.POST, "/api/watchlists/" + watchlistId + "/items",
                Map.of("companyId", companyId, "scoreDropThreshold", 10), token, null);
        assertThat(added.body().path("items").get(0).path("latestScore").asInt()).isEqualTo(77);
        ObjectNode worse = (ObjectNode) JsonMapper.shared().readTree(fixture);
        ((ObjectNode) worse.path("health")).put("score", 60).put("band", "STABLE");
        worse.put("as_of", LocalDate.now().toString());
        when(ml.analyze(anyString(), anyString(), any(), any(), any(), anyBoolean())).thenReturn(analysis(worse.toString()));
        Res job = call(HttpMethod.POST, "/api/companies/" + companyId + "/analyze", Map.of(), token, null);
        assertThat(job.status()).isEqualTo(202);
        awaitJob(job.body().path("id").asString());
        JsonNode alerts = get("/api/alerts", token).body();
        assertThat(alerts).anyMatch(a -> "SCORE_DROP".equals(a.path("type").asString())
                && a.path("message").asString().contains("fell 17 points"));

        // exports: CSV on every plan, PDF needs Pro -> plan-limit, then demo checkout unlocks it
        assertThat(get("/api/reports/" + reportId + "/export?format=csv", token).status()).isEqualTo(200);
        Res pdfFree = get("/api/reports/" + reportId + "/export?format=pdf", token);
        assertThat(pdfFree.status()).isEqualTo(403);
        assertThat(pdfFree.body().path("type").asString()).endsWith("/plan-limit");
        Res checkout = call(HttpMethod.POST, "/api/billing/checkout", Map.of("plan", "PRO"), token, null);
        assertThat(checkout.body().path("user").path("plan").asString()).isEqualTo("PRO");
        Res pdf = get("/api/reports/" + reportId + "/export?format=pdf", token);
        assertThat(pdf.status()).isEqualTo(200);
        assertThat(new String(pdf.raw(), 0, 4, StandardCharsets.US_ASCII)).isEqualTo("%PDF");

        // API key: created once, then authenticates programmatic calls
        Res key = call(HttpMethod.POST, "/api/me/api-keys", Map.of("name", "notebook"), token, null);
        assertThat(key.status()).isEqualTo(201);
        Res viaKey = call(HttpMethod.GET, "/api/auth/me", null, null, key.body().path("secret").asString());
        assertThat(viaKey.status()).isEqualTo(200);
        assertThat(viaKey.body().path("usage").path("apiCallsToday").asLong()).isGreaterThanOrEqualTo(1);
        assertThat(call(HttpMethod.GET, "/api/auth/me", null, null, "echo_invalid").status()).isEqualTo(401);

        // RBAC: admin endpoints are closed to normal users and open to admins
        assertThat(get("/api/admin/users", token).status()).isEqualTo(403);
        assertThat(get("/api/admin/users", register("admin@test.dev")).status()).isEqualTo(200);
    }

    @Test
    void validationAndAuthErrorsAreProblemDetails() {
        Res bad = call(HttpMethod.POST, "/api/auth/register", Map.of("email", "not-an-email", "password", "x"), null, null);
        assertThat(bad.status()).isEqualTo(400);
        assertThat(bad.body().path("errors").has("email")).isTrue();
        assertThat(get("/api/watchlists", null).status()).isEqualTo(401);
        Res login = call(HttpMethod.POST, "/api/auth/login", Map.of("email", "nobody@test.dev", "password", "wrong-pass"),
                null, null);
        assertThat(login.status()).isEqualTo(401);
    }
}
