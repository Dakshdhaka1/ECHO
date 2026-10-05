package com.echo.controller;

import com.echo.dto.Dtos.AnalyzeRequest;
import com.echo.dto.Dtos.CompanyDto;
import com.echo.dto.Dtos.CompareItemDto;
import com.echo.dto.Dtos.RadarDto;
import com.echo.dto.Dtos.HistoryPointDto;
import com.echo.dto.Dtos.JobDto;
import com.echo.dto.Dtos.ReportDto;
import com.echo.dto.Dtos.ReportEnvelope;
import com.echo.dto.Dtos.SearchResultDto;
import com.echo.exception.ApiException;
import com.echo.security.CurrentUser;
import com.echo.service.AnalysisService;
import com.echo.service.CompanyService;
import com.echo.service.ExportService;
import com.echo.service.InsightService;
import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.tags.Tag;
import jakarta.servlet.http.HttpServletRequest;
import java.time.LocalDate;
import java.util.List;
import java.util.UUID;
import org.springframework.format.annotation.DateTimeFormat;
import org.springframework.http.ContentDisposition;
import org.springframework.http.HttpHeaders;
import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api")
@Tag(name = "Companies & reports", description = "Search, health reports, analysis jobs, history, comparison, export")
public class CompanyController {

    private final CompanyService companies;
    private final AnalysisService analysis;
    private final InsightService insights;
    private final ExportService exports;

    public CompanyController(CompanyService companies, AnalysisService analysis, InsightService insights,
                             ExportService exports) {
        this.companies = companies;
        this.analysis = analysis;
        this.insights = insights;
        this.exports = exports;
    }

    @GetMapping("/companies/search")
    @Operation(summary = "Resolve a company name, ticker or former name to SEC filers")
    public List<SearchResultDto> search(@RequestParam("q") String q) {
        return companies.search(q);
    }

    @GetMapping("/companies/{id}")
    public CompanyDto company(@PathVariable Long id) {
        return CompanyDto.of(companies.get(id));
    }

    @GetMapping("/companies/{id}/report")
    @Operation(summary = "Latest health report (200), or 202 with the analysis job producing it",
            description = "asOf (yyyy-MM-dd) requests a point-in-time report, e.g. a historical case study.")
    public ResponseEntity<ReportEnvelope> report(@PathVariable Long id,
                                                 @RequestParam(required = false) @DateTimeFormat(iso = DateTimeFormat.ISO.DATE) LocalDate asOf,
                                                 HttpServletRequest request) {
        ReportEnvelope env = analysis.report(id, asOf, CurrentUser.id().orElse(null), request.getRemoteAddr());
        return ResponseEntity.status("READY".equals(env.status()) ? HttpStatus.OK : HttpStatus.ACCEPTED).body(env);
    }

    @PostMapping("/companies/{id}/analyze")
    @Operation(summary = "Force a fresh analysis (counts against the plan's daily quota)")
    public ResponseEntity<JobDto> analyze(@PathVariable Long id, @RequestBody(required = false) AnalyzeRequest body) {
        JobDto job = analysis.refresh(id, body == null ? null : body.asOf(), CurrentUser.require());
        return ResponseEntity.accepted().body(job);
    }

    @GetMapping("/jobs/{id}")
    @Operation(summary = "Analysis job status; reportId is set when DONE")
    public JobDto job(@PathVariable UUID id) {
        return analysis.job(id);
    }

    @GetMapping("/reports/{id}")
    public ReportDto reportById(@PathVariable Long id) {
        return analysis.reportById(id);
    }

    @GetMapping("/companies/{id}/history")
    @Operation(summary = "Score history: LIVE reports and point-in-time BACKFILL points (Free plan: 12 months)")
    public List<HistoryPointDto> history(@PathVariable Long id,
                                         @RequestParam(required = false) @DateTimeFormat(iso = DateTimeFormat.ISO.DATE) LocalDate from,
                                         @RequestParam(required = false) @DateTimeFormat(iso = DateTimeFormat.ISO.DATE) LocalDate to) {
        return insights.history(id, from, to, CurrentUser.id().orElse(null));
    }

    @GetMapping("/radar")
    @Operation(summary = "Signals radar: health score vs distress probability for every analysed demo-universe report")
    public RadarDto radar() {
        return insights.radar();
    }

    @GetMapping("/compare")
    @Operation(summary = "Latest pillar scores side by side (Free: 2 companies, Pro: 4, Enterprise: 8)")
    public List<CompareItemDto> compare(@RequestParam List<Long> ids) {
        return insights.compare(ids, CurrentUser.id().orElse(null));
    }

    @GetMapping("/reports/{id}/export")
    @Operation(summary = "Export a report as CSV (all plans) or PDF (Pro and Enterprise)")
    public ResponseEntity<byte[]> export(@PathVariable Long id, @RequestParam(defaultValue = "pdf") String format) {
        Long userId = CurrentUser.require();
        ReportDto report = analysis.reportById(id);
        String base = "echo-" + (report.company().ticker() == null ? report.company().marketId() : report.company().ticker())
                + "-" + report.asOf();
        byte[] body;
        MediaType type;
        switch (format.toLowerCase()) {
            case "csv" -> { body = exports.csv(report, userId); type = new MediaType("text", "csv"); }
            case "pdf" -> { body = exports.pdf(report, userId); type = MediaType.APPLICATION_PDF; }
            default -> throw ApiException.badRequest("format must be csv or pdf");
        }
        return ResponseEntity.ok().contentType(type)
                .header(HttpHeaders.CONTENT_DISPOSITION,
                        ContentDisposition.attachment().filename(base + "." + format.toLowerCase()).build().toString())
                .body(body);
    }
}
