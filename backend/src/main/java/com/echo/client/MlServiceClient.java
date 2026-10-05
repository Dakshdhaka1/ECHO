package com.echo.client;

import com.echo.config.EchoProperties;
import com.echo.exception.ApiException;
import java.time.Duration;
import java.time.LocalDate;
import java.util.LinkedHashMap;
import java.util.Map;
import java.util.function.Supplier;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.slf4j.MDC;
import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.http.client.SimpleClientHttpRequestFactory;
import org.springframework.stereotype.Component;
import org.springframework.web.client.ResourceAccessException;
import org.springframework.web.client.RestClient;
import org.springframework.web.client.RestClientResponseException;
import tools.jackson.databind.JsonNode;
import tools.jackson.databind.ObjectMapper;

/**
 * Client for the internal ML service (ARCHITECTURE §7.2). The analysis call can take minutes in live mode
 * (rate-limited public sources), so it has its own long read timeout; lookups use a short one and retry once.
 */
@Component
public class MlServiceClient {

    private static final Logger log = LoggerFactory.getLogger(MlServiceClient.class);

    private final RestClient fast;
    private final RestClient slow;
    private final ObjectMapper mapper;
    private final String adminToken;

    public MlServiceClient(RestClient.Builder builder, EchoProperties props, ObjectMapper mapper) {
        this.fast = builder.clone().baseUrl(props.mlServiceUrl()).requestFactory(factory(5, 30)).build();
        this.slow = builder.clone().baseUrl(props.mlServiceUrl())
                .requestFactory(factory(5, props.analysis().mlTimeoutSeconds())).build();
        this.mapper = mapper;
        this.adminToken = props.mlAdminToken();
    }

    private static SimpleClientHttpRequestFactory factory(int connectSeconds, int readSeconds) {
        SimpleClientHttpRequestFactory f = new SimpleClientHttpRequestFactory();
        f.setConnectTimeout(Duration.ofSeconds(connectSeconds));
        f.setReadTimeout(Duration.ofSeconds(readSeconds));
        return f;
    }

    public JsonNode resolve(String query, int limit) {
        return withRetry(() -> post(fast, "/v1/resolve", Map.of("query", query, "limit", limit)));
    }

    /** Full AnalysisResult as raw JSON text (stored verbatim as the report payload) plus its parsed tree. */
    public record Analysis(String json, JsonNode tree) {
    }

    public Analysis analyze(String market, String marketId, String ticker, String name, LocalDate asOf,
                            boolean includeBackfill) {
        Map<String, Object> company = new LinkedHashMap<>();
        company.put("market", market);
        company.put("market_id", marketId);
        if (ticker != null) company.put("ticker", ticker);
        if (name != null) company.put("name", name);
        Map<String, Object> body = new LinkedHashMap<>();
        body.put("company", company);
        body.put("as_of", asOf == null ? null : asOf.toString());
        body.put("include_backfill", includeBackfill);
        String json = call(() -> slow.post().uri("/v1/analyze").contentType(MediaType.APPLICATION_JSON)
                .header("X-Request-Id", MDC.get("requestId")).body(body).retrieve().body(String.class));
        return new Analysis(json, mapper.readTree(json));
    }

    public JsonNode universe() {
        return withRetry(() -> get(fast, "/v1/universe"));
    }

    public JsonNode models() {
        return withRetry(() -> get(fast, "/v1/models"));
    }

    public JsonNode health() {
        return get(fast, "/health");
    }

    public JsonNode sentiment(java.util.List<String> texts) {
        return post(fast, "/v1/sentiment", Map.of("texts", texts));
    }

    public JsonNode monitoring() {
        return get(fast, "/v1/monitoring");
    }

    public JsonNode runMonitoring() {
        return post(slow, "/v1/monitoring/run", Map.of());
    }

    public JsonNode retrain(String model, boolean promote) {
        return parse(call(() -> fast.post().uri("/v1/admin/retrain").contentType(MediaType.APPLICATION_JSON)
                .header("X-Admin-Token", adminToken).body(Map.of("model", model, "promote", promote))
                .retrieve().body(String.class)));
    }

    public JsonNode retrainJobs() {
        return parse(call(() -> fast.get().uri("/v1/admin/retrain").header("X-Admin-Token", adminToken)
                .retrieve().body(String.class)));
    }

    // ------------------------------------------------------------------ plumbing
    private JsonNode get(RestClient client, String path) {
        return parse(call(() -> client.get().uri(path).retrieve().body(String.class)));
    }

    private JsonNode post(RestClient client, String path, Object body) {
        return parse(call(() -> client.post().uri(path).contentType(MediaType.APPLICATION_JSON).body(body)
                .retrieve().body(String.class)));
    }

    private JsonNode parse(String json) {
        return mapper.readTree(json == null ? "null" : json);
    }

    private static <T> T call(Supplier<T> request) {
        try {
            return request.get();
        } catch (RestClientResponseException e) {
            String detail = detail(e);
            if (e.getStatusCode().value() == 404) {
                throw new ApiException(HttpStatus.NOT_FOUND, "not-found", detail);
            }
            if (e.getStatusCode().value() == 409) {
                throw ApiException.conflict(detail);
            }
            if (e.getStatusCode().is4xxClientError()) {
                throw new ApiException(HttpStatus.BAD_REQUEST, "ml-rejected", detail);
            }
            throw ApiException.mlUnavailable("ML service error: " + detail);
        } catch (ResourceAccessException e) {
            throw ApiException.mlUnavailable("ML service unreachable: " + e.getMessage());
        }
    }

    private static String detail(RestClientResponseException e) {
        String body = e.getResponseBodyAsString();
        int i = body.indexOf("\"detail\":");
        if (i >= 0) {
            return body.substring(i + 9).replaceAll("^\"|\"?}\\s*$", "");
        }
        return e.getStatusText();
    }

    private static JsonNode withRetry(Supplier<JsonNode> request) {
        try {
            return request.get();
        } catch (ApiException e) {
            if (e.getStatus() != HttpStatus.SERVICE_UNAVAILABLE) {
                throw e;
            }
            log.info("ML call failed ({}); retrying once", e.getMessage());
            return request.get();
        }
    }
}
