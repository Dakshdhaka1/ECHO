package com.echo.controller;

import com.echo.client.MlServiceClient;
import com.echo.dto.Dtos.AdminUserUpdate;
import com.echo.dto.Dtos.RetrainRequest;
import com.echo.dto.Dtos.StatsDto;
import com.echo.dto.Dtos.UserDto;
import com.echo.service.AdminService;
import com.echo.service.CompanyService;
import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.tags.Tag;
import jakarta.validation.Valid;
import java.util.List;
import java.util.Map;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PatchMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;
import tools.jackson.databind.JsonNode;

/** Public platform info (demo universe, model cards, stats, NLP playground) and admin MLOps endpoints. */
@RestController
@RequestMapping("/api")
@Tag(name = "Platform & MLOps")
public class PlatformController {

    private final CompanyService companies;
    private final AdminService admin;
    private final MlServiceClient ml;

    public PlatformController(CompanyService companies, AdminService admin, MlServiceClient ml) {
        this.companies = companies;
        this.admin = admin;
        this.ml = ml;
    }

    @GetMapping("/universe")
    @Operation(summary = "Demo companies with recorded data, including historical case-study dates")
    public List<JsonNode> universe() {
        return companies.universe();
    }

    @GetMapping("/models")
    @Operation(summary = "Model cards: data, metrics vs baseline, gate decision, intended use and limitations")
    public JsonNode models() {
        return ml.models();
    }

    @GetMapping("/stats")
    public StatsDto stats() {
        return admin.stats();
    }

    @PostMapping("/sentiment")
    @Operation(summary = "Score headlines with the news-sentiment champion model (signed-in users)")
    public JsonNode sentiment(@RequestBody Map<String, List<String>> body) {
        List<String> texts = body.getOrDefault("texts", List.of());
        return ml.sentiment(texts.subList(0, Math.min(texts.size(), 50)));
    }

    // ---------------------------------------------------------------- admin
    @GetMapping("/admin/users")
    public List<UserDto> users() {
        return admin.users();
    }

    @PatchMapping("/admin/users/{id}")
    public UserDto updateUser(@PathVariable Long id, @RequestBody AdminUserUpdate req) {
        return admin.updateUser(id, req.plan(), req.role());
    }

    @GetMapping("/admin/jobs")
    public List<JsonNode> jobs() {
        return admin.recentJobs();
    }

    @GetMapping("/admin/monitoring")
    @Operation(summary = "Latest drift (PSI) / freshness monitoring report from the ML service")
    public JsonNode monitoring() {
        return ml.monitoring();
    }

    @PostMapping("/admin/monitoring/run")
    public JsonNode runMonitoring() {
        return ml.runMonitoring();
    }

    @GetMapping("/admin/retrain")
    public JsonNode retrainJobs() {
        return ml.retrainJobs();
    }

    @PostMapping("/admin/retrain")
    @Operation(summary = "Retrain a model; the ML service's promotion gate decides whether it becomes champion")
    public ResponseEntity<JsonNode> retrain(@Valid @RequestBody RetrainRequest req) {
        return ResponseEntity.accepted().body(ml.retrain(req.model(), req.promote() == null || req.promote()));
    }

    @GetMapping("/admin/ml-health")
    public JsonNode mlHealth() {
        return ml.health();
    }
}
